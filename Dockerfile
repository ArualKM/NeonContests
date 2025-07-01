# Dockerfile for Discord Music Contest Bot
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY *.py ./
COPY .env .env

# Create directories
RUN mkdir -p backups logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_FILE=/app/logs/bot.log
ENV DATABASE_PATH=/app/data/suno_contests.db
ENV BACKUP_DIR=/app/data/backups

# Create volume mount points
VOLUME ["/app/data", "/app/logs"]

# Run the bot
CMD ["python", "run.py"]
