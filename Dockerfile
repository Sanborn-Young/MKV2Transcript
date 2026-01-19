FROM python:3.11-slim

# Install FFmpeg and git
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# Install PyTorch 2.6 to match local working environment
RUN pip install --no-cache-dir torch==2.6.0 torchaudio==2.6.0

# Install Python dependencies
RUN pip install --no-cache-dir whisperx gradio pandas tqdm

WORKDIR /app
COPY app.py /app/

# Mount point for host files
VOLUME ["/data"]

EXPOSE 7860
CMD ["python", "app.py"]
