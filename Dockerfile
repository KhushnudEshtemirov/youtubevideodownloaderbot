# Python 3.12 — matches the version confirmed to work with python-telegram-bot 21.6
FROM python:3.12-slim

# ffmpeg is required by yt-dlp for merging video/audio and extracting mp3 audio
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# No port is exposed on purpose: this is a background worker (polling),
# not a web service — it doesn't listen for incoming HTTP requests.
CMD ["python", "bot.py"]
