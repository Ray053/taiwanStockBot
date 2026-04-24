FROM python:3.11-slim
LABEL "language"="python"
LABEL "framework"="fastapi"

WORKDIR /app

# System deps + Node.js 20 for React build
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Frontend build (outputs to /app/static via vite outDir: '../static')
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci

COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# Application code
COPY . .

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
