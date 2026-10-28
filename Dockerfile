# syntax=docker/dockerfile:1

# ---- Builder stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends build-essential gcc && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# ---- Production stage ----
FROM python:3.11-slim

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY --from=builder /app /app

# Create non‑root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Expose Flask default port
EXPOSE 5000

# Environment variables for Flask
ENV FLASK_APP=run.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_ENV=production

# Command to run the app
CMD ["python", "run.py"]
