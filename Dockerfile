# Two images from one file: the API (light) and the worker (adds Tesseract for scanned CVs).
#   docker build --target api .
#   docker build --target worker .

FROM python:3.13-slim AS api
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM api AS worker
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
CMD ["python", "-m", "worker.main"]
