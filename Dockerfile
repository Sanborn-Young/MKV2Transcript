FROM python:3.11-slim

# Install FFmpeg and git
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (no PyTorch needed - faster-whisper manages it)
RUN pip install --no-cache-dir faster-whisper gradio pandas tqdm

WORKDIR /app
COPY app.py /app/

VOLUME ["/data"]

EXPOSE 7860
CMD ["python", "app.py"]
