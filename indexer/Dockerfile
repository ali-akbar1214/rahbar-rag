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

# Copy installed Python packages from builder, upgrade pip/setuptools, and purge any bundled old setuptools wheels/metadata
COPY --from=builder /install /usr/local
RUN pip install --no-cache-dir --upgrade pip "setuptools>=78.1.1" && \
    rm -rf /usr/local/lib/python3.12/ensurepip /usr/lib/python3.12/ensurepip /usr/share/python-wheels && \
    python3 -c 'import pathlib, shutil, zipfile; roots = [pathlib.Path(r) for r in ("/usr","/var","/opt","/root") if pathlib.Path(r).exists()]; [shutil.rmtree(d, ignore_errors=True) for r in roots for d in list(r.rglob("setuptools*")) if d.is_dir() and d.suffix in (".dist-info",".egg-info") and not d.name.startswith("setuptools-78.") and not d.name.startswith("setuptools-79.") and not d.name.startswith("setuptools-8")]; [f.unlink(missing_ok=True) for r in roots for f in list(r.rglob("*setuptools*")) if f.is_file() and ("70." in f.name or (f.suffix == ".egg-info" and "Version: 70." in f.read_text(errors="ignore")))]; [p.unlink(missing_ok=True) for r in roots for p in list(r.rglob("*")) if p.is_file() and p.suffix in (".whl",".zip",".egg") and zipfile.is_zipfile(p) and any("setuptools-70." in n for n in zipfile.ZipFile(p).namelist())]'

# Copy pipeline package code
COPY pipeline/ ./pipeline/

RUN chown -R nonroot:appgroup /app

USER nonroot

ENTRYPOINT ["python", "-m", "pipeline.run"]
CMD []
