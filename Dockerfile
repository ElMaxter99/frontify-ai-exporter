FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 EXPORT_DIR=/exports EXPORT_DIR_LOCKED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && mkdir -p /exports
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8765/api/config')" || exit 1
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "src", "ui", "--host", "0.0.0.0", "--port", "8765", "--no-browser"]
