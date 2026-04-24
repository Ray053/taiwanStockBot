FROM python:3.11-slim
LABEL "language"="python"
LABEL "framework"="fastapi"

WORKDIR /app

# System deps for Python packages + curl for nodesource
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Frontend deps
COPY frontend/package.json frontend/
RUN cd frontend && npm install

# App source
COPY . .

EXPOSE 3000

CMD ["/bin/sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8080 & cd /app/frontend && npm run dev"]
