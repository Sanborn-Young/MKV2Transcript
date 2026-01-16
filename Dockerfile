FROM python:3.11-slim

# Install FFmpeg and Intel optimizations
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir faster-whisper gradio pandas tqdm

WORKDIR /app
COPY app.py /app/

# Mount point for host files
VOLUME ["/data"]

EXPOSE 7860
CMD ["python", "app.py"]