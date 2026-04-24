FROM python:3.12-slim

WORKDIR /app

# ffmpeg so faster-whisper accepts non-WAV inputs; libgomp1 for CTranslate2.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV HOST=0.0.0.0
ENV PORT=8081
ENV STT_MODEL=small.en
ENV STT_DEVICE=cpu
ENV STT_COMPUTE=int8

# The whisper model downloads on first run; persist across container
# restarts by mounting a cache volume at this path.
ENV HF_HOME=/app/cache/huggingface
VOLUME ["/app/cache"]

EXPOSE 8081

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request,sys,os; sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8081\")}/health').status==200 else 1)"

CMD ["python", "server.py"]
