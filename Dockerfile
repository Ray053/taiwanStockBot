FROM python:3.11-slim
LABEL "language"="python"
LABEL "framework"="fastapi"

WORKDIR /app

# Python + Node.js system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App source (npm install happens at runtime, not here)
COPY . .

EXPOSE 8080

# At startup: install frontend deps, build to static/, then start FastAPI
CMD ["/bin/sh", "-c", "cd /app/frontend && npm install && npm run build && cd /app && uvicorn app.main:app --host 0.0.0.0 --port 8080"]
