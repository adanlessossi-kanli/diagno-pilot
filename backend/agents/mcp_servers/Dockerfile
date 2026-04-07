FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./backend/

ENV SERVER_PORT=8000
EXPOSE ${SERVER_PORT}

CMD ["python", "-m", "backend.agents.mcp_servers.base_server"]
