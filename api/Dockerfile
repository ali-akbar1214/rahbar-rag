# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim AS runner

WORKDIR /app

# Upgrade OS packages to patch fixable CVEs
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Create unprivileged non-root user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/false -m nonroot

# Copy installed Python packages from builder, then upgrade pip/setuptools so old dist-info is uninstalled
COPY --from=builder /install /usr/local
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" && \
    rm -rf /usr/local/lib/python3.12/ensurepip

# Copy application code
COPY app/ ./app/

# Set ownership to non-root user
RUN chown -R nonroot:appgroup /app

USER nonroot

EXPOSE 8000

ENTRYPOINT ["uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8000"]
