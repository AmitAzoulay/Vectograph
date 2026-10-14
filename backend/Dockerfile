# Backend image - Python 3.11 slim for a small footprint.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY app ./app

EXPOSE 8000

# `--reload` gives a smooth developer experience behind the volume mount.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
