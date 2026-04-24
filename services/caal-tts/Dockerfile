# piper-phonemize 1.1.0 ships Linux wheels for Python 3.10/3.11 only (no
# 3.12 Linux wheel as of the current release). Pin to 3.11-slim so the
# pip install resolves without needing to compile phonemize from source.
# Both linux/amd64 and linux/arm64 wheels exist at 3.11, so no --platform
# pin is required.
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV HOST=0.0.0.0
ENV PORT=8082
ENV TTS_VOICE=en_US-ryan-high
ENV TTS_VOICE_DIR=/app/voices

# Piper voices download on first use. Mount a named volume at /app/voices
# to persist them across container restarts.
VOLUME ["/app/voices"]

EXPOSE 8082

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys,os; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8082\")}/health').status==200 else 1)"

CMD ["python", "server.py"]
