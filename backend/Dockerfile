FROM python:3.12-slim
WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . ./backend/

# Create non-root user (UID 1001, no login shell)
RUN adduser --system --uid 1001 --no-create-home appuser
USER appuser

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
