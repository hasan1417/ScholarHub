FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies + TeX Live
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
        texlive-latex-base \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-fonts-extra \
        texlive-science \
        texlive-bibtex-extra \
        texlive-publishers \
        texlive-xetex \
        texlive-lang-arabic \
        latexmk \
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
