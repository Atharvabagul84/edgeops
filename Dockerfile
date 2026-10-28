FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN useradd --create-home --uid 10001 edgeops && mkdir /data && chown edgeops:edgeops /data
COPY --chown=edgeops:edgeops backend/ backend/
COPY --chown=edgeops:edgeops frontend/ frontend/
USER edgeops
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=2)" || exit 1
CMD ["python", "-m", "backend.server", "--host", "0.0.0.0", "--port", "8765", "--data", "/data/edgeops.sqlite3"]
