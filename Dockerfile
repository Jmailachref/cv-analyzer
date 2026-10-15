# Two images from one file: the API with the web app (light) and the worker (adds Tesseract for scanned CVs).
#   docker build --target api .
#   docker build --target worker .

FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY web/ .
RUN npm run build

FROM python:3.13-slim AS api
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=web /web/dist web/dist
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

FROM api AS worker
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
CMD ["python", "-m", "worker.main"]
