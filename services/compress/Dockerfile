FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for torch and other packages
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Build context is the REPO ROOT (the default for Render/Fly/Railway and for
# `docker build -f services/compress/Dockerfile .`), so reference files from there.
COPY services/compress/requirements.txt .

# Install Python dependencies
# Note: torch CPU is large (~2GB); the full image will be ~3-4GB.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/compress/app.py .

# Expose port
EXPOSE 8080

# Health check — uses stdlib urllib so no extra dependency is required.
# Long start-period: the model loads on first startup (can take 30-120s).
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8080/health',timeout=5).status==200 else 1)" || exit 1

# Run the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
