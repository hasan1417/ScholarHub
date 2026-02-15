FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies
ARG TECTONIC_VERSION=0.15.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gcc \
        postgresql-client \
        pandoc \
        libfontconfig1 \
        fonts-hosny-amiri \
        ffmpeg \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
        amd64) tectonic_arch="x86_64-unknown-linux-gnu" ;; \
        arm64) tectonic_arch="aarch64-unknown-linux-musl" ;; \
        armhf) tectonic_arch="arm-unknown-linux-musleabihf" ;; \
        *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40${TECTONIC_VERSION}/tectonic-${TECTONIC_VERSION}-${tectonic_arch}.tar.gz" -o /tmp/tectonic.tar.gz \
    && tar -xzf /tmp/tectonic.tar.gz -C /tmp \
    && install -m 0755 /tmp/tectonic /usr/local/bin/tectonic \
    && rm -rf /tmp/tectonic* \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Note: Marker ML models (~1.5GB) are downloaded on first PDF processing.
# pdfplumber is used as fallback until models are ready.
# To pre-download: docker exec backend python -c "from marker.models import create_model_dict; create_model_dict()"

# Copy project
COPY . .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
