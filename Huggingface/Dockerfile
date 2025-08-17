# Use Python 3.9 slim image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create writable directories
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Set environment variables
ENV PORT=7860
ENV PYTHONUNBUFFERED=1
ENV SECRET_KEY=your_strong_secret_key_here
ENV UPDATE_INTERVAL=600
ENV MAX_WORKERS=3
ENV REQUEST_TIMEOUT=15
ENV CACHE_EXPIRY=300
ENV DEBUG=False

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY app.py .

# Expose the port Hugging Face Spaces uses
EXPOSE 7860

# Run the application
CMD ["python", "app.py"]