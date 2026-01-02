# Multi-stage Dockerfile for deployment
# Supports: Fly.io, Railway, Render, Oracle Cloud

FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory
RUN mkdir -p logs

# Expose ports
EXPOSE 8502 8080

# Default command (can be overridden)
CMD ["streamlit", "run", "optionchain.py", "--server.port=8502", "--server.headless=true"]
