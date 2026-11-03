# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

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

# Copy installed Python packages from builder, upgrade setuptools, and remove pip/ensurepip from runtime image
COPY --from=builder /install /usr/local
RUN pip install --no-cache-dir --upgrade "setuptools>=78.1.1" && \
    python3 -m pip uninstall -y pip && \
    rm -rf /usr/local/lib/python3.12/ensurepip /usr/lib/python3.12/ensurepip /usr/share/python-wheels

# Copy pipeline package code
COPY pipeline/ ./pipeline/

RUN chown -R nonroot:appgroup /app

USER nonroot

ENTRYPOINT ["python", "-m", "pipeline.run"]
CMD []
