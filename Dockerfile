# Backend
FROM python:3.12-slim AS backend
WORKDIR /app/backend
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install --with-deps chromium
COPY backend/ .
EXPOSE 8000
CMD ["python", "run_backend.py"]

# Frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
