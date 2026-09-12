# Multi-stage build: compile the React frontend, then serve it and the API from one
# FastAPI process — matching the "Single-Command Production Serving" design in README.md.

FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV APP_ENV=production
ENV APP_HOST=0.0.0.0
# Most hosts (Render, Railway, Fly.io) inject PORT at runtime; 8000 is the local default.
ENV APP_PORT=8000
EXPOSE 8000

# Shell form so $PORT (injected by the host) is honored if set, falling back to APP_PORT.
CMD uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-$APP_PORT}
