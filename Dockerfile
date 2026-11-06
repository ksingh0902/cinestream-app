# ==========================================
# Stage 1: Build Modern React Frontend
# ==========================================
FROM node:24-alpine AS frontend-builder
WORKDIR /build

# Ensure npm is pinned to verified version
RUN npm install -g npm@11.11.0

# Copy dependency manifests first for layer caching
COPY Cinemy/package.json Cinemy/package-lock.json ./
RUN npm ci

# Copy frontend source and build production bundle
COPY Cinemy/ ./
RUN npm run build

# ==========================================
# Stage 2: Python FastAPI Runtime
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Copy compiled React assets into FastAPI static directory
COPY --from=frontend-builder /build/dist/ ./server/static/

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn server.app:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-1}"]
