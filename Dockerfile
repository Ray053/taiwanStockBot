FROM python:3.11-slim

WORKDIR /app

# System deps + Node.js 20 (needed to build the React frontend)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc libpq-dev curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Frontend build ─────────────────────────────────────────────────────────────
# Copy package files first for better layer caching
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci

COPY frontend/ ./frontend/
# vite outDir is '../static' relative to frontend/ → outputs to /app/static
RUN cd frontend && npm run build

# ── Application code ───────────────────────────────────────────────────────────
# Host repo has no static/ dir (.gitignore), so /app/static from npm build is safe
COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
