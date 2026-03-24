"""
File endpoints — upload clinical files to S3 and retrieve presigned URLs.
Implements REQ-07 (clinical file management).
"""
from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from backend.core.auth import get_current_user
from backend.core.database import db
from backend.models.patient_file import PatientFile
from backend.services.s3_service import s3_service

router = APIRouter(prefix="/files", tags=["files"])


class PatientFileResponse(PatientFile):
    download_url: str | None = None


@router.post("/upload", response_model=PatientFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile,
    patient_id: str = Form(...),
    consultation_id: str | None = Form(default=None),
    file_type: str = Form(default="pdf"),
    current_user: dict = Depends(get_current_user),
):
    """POST /api/v1/files/upload — upload a clinical file to S3 and persist metadata."""
    # Upload to S3
    s3_key = await s3_service.upload(file=file, patient_id=patient_id)

    # Persist metadata to MongoDB
    now = datetime.utcnow()
    doc = {
        "patient_id": ObjectId(patient_id),
        "consultation_id": ObjectId(consultation_id) if consultation_id else None,
        "file_type": file_type,
        "s3_key": s3_key,
        "original_name": file.filename or "unknown",
        "size_bytes": file.size or 0,
        "uploaded_by": ObjectId(str(current_user["_id"])),
        "created_at": now,
    }

    database = db.get_db()
    result = await database["patient_files"].insert_one(doc)

    return PatientFileResponse(
        id=str(result.inserted_id),
        patient_id=patient_id,
        consultation_id=consultation_id,
        file_type=file_type,
        s3_key=s3_key,
        original_name=doc["original_name"],
        size_bytes=doc["size_bytes"],
        uploaded_by=str(current_user["_id"]),
        created_at=now,
        download_url=None,
    )


@router.get("/{file_id}", response_model=PatientFileResponse, status_code=status.HTTP_200_OK)
async def get_file(
    file_id: str,
    current_user: dict = Depends(get_current_user),
):
    """GET /api/v1/files/{file_id} — retrieve file metadata and a presigned S3 URL."""
    try:
        oid = ObjectId(file_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    database = db.get_db()
    doc = await database["patient_files"].find_one({"_id": oid})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    download_url = await s3_service.get_presigned_url(doc["s3_key"])

    return PatientFileResponse(
        id=str(doc["_id"]),
        patient_id=str(doc["patient_id"]),
        consultation_id=str(doc["consultation_id"]) if doc.get("consultation_id") else None,
        file_type=doc["file_type"],
        s3_key=doc["s3_key"],
        original_name=doc["original_name"],
        size_bytes=doc["size_bytes"],
        uploaded_by=str(doc["uploaded_by"]),
        created_at=doc.get("created_at"),
        download_url=download_url,
    )
