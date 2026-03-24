"""
Reusable FastAPI authentication and authorization dependencies.

Other routers should import `get_current_user`, `require_role`, and
`oauth2_scheme` from here instead of duplicating the logic.

`audit_dependency` provides a ready-made FastAPI dependency that logs a
sensitive action after the route handler runs.
"""

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from bson import ObjectId

from backend.core.config import settings
from backend.core.database import db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """Decode JWT, fetch user from DB, return user document as dict."""
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exc
    except JWTError:
        raise credentials_exc

    try:
        oid = ObjectId(user_id)
    except Exception:
        raise credentials_exc

    database = db.get_db()
    user_doc = await database["users"].find_one({"_id": oid})
    if user_doc is None:
        raise credentials_exc

    return user_doc


def require_role(roles: list[str]):
    """Return a FastAPI dependency that enforces role-based access.

    Raises HTTP 403 if the authenticated user's role is not in *roles*.

    Usage::

        @router.get("/admin/users", dependencies=[Depends(require_role(["admin"]))])
        async def list_users(): ...

        # or inject the user at the same time:
        @router.get("/admin/users")
        async def list_users(user: dict = Depends(require_role(["admin"]))): ...
    """
    async def _check(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _check


def audit_dependency(action: str, resource: str):
    """Return a FastAPI dependency that logs an audit entry for the current request.

    Designed to be used in route `dependencies=[...]` or as an injected param.

    Usage::

        @router.post(
            "/patients",
            dependencies=[Depends(audit_dependency("create_patient", "patients"))],
        )
        async def create_patient(...): ...
    """
    async def _audit(
        request: Request,
        current_user: dict = Depends(get_current_user),
    ) -> None:
        from backend.services.audit_service import audit_service  # avoid circular import

        ip = request.client.host if request.client else None
        await audit_service.log_action(
            user_id=str(current_user["_id"]),
            action=action,
            resource=resource,
            ip_address=ip,
        )

    return _audit
