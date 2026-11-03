# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Install system dependencies for OCR and PDF rendering and apply OS security upgrades
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils && \
    rm -rf /var/lib/apt/lists/*

# Create unprivileged non-root user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/false -m nonroot

# Copy installed Python packages from builder, then upgrade pip/setuptools so old dist-info is uninstalled
COPY --from=builder /install /usr/local
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" && \
    rm -rf /usr/local/lib/python3.12/ensurepip

# Copy pipeline package code
COPY pipeline/ ./pipeline/

RUN chown -R nonroot:appgroup /app

USER nonroot

ENTRYPOINT ["python", "-m", "pipeline.run"]
CMD []
