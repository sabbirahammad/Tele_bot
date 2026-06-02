FROM python:3.11-slim

# Install system dependencies required for building C extensions (like TgCrypto)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create the database directory and ensure it has correct permissions
RUN mkdir -p /app/database

# The VOLUME instruction is mostly documentation for Railway; 
# handle persistence via Railway's Volume mounting UI.
VOLUME ["/app/database"]

CMD ["python", "main.py"]