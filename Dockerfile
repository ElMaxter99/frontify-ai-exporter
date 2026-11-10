# ---- stage 1: build the React UI ----
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: API + exporter ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 WEB_DIST=/app/frontend/dist EXPORT_DIR=/exports DATA_DIR=/data
WORKDIR /app
# Optional: build with --build-arg EXTRAS="chromadb faiss-cpu qdrant-client sentence-transformers pytesseract" (+ tesseract-ocr)
ARG EXTRAS=""
COPY requirements.txt ./
RUN pip install -r requirements.txt && if [ -n "$EXTRAS" ]; then pip install $EXTRAS; fi
COPY src ./src
COPY --from=ui /ui/dist ./frontend/dist
RUN useradd -m app && mkdir -p /exports /data && chown -R app /exports /data /app
USER app
VOLUME ["/exports", "/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/api/settings')" || exit 1
CMD ["python", "-m", "src.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
