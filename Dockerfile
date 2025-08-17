# Use Python official image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY rdslive.epg.py .

# Rename file to remove spaces (Docker doesn't like spaces in filenames)
RUN mv "rdslive.epg.py" app.py

# Create directory for generated files
RUN mkdir -p /app/generated

# Expose port 5000
EXPOSE 5000

# Set environment variables
ENV SECRET_KEY=your_strong_secret_key_here
ENV BASE_URL=https://rds.live
ENV UPDATE_INTERVAL=300
ENV MAX_WORKERS=5
ENV REQUEST_TIMEOUT=15
ENV CACHE_EXPIRY=180
ENV PORT=5000
ENV DEBUG=False
ENV EPG_URL=http://epg.iptv.ro/epg.xml
ENV EPG_UPDATE_INTERVAL=3600

# Run the application
CMD ["python", "app.py"]
