FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    WORK_DIR=/tmp/modupdf HOME=/tmp OMP_THREAD_LIMIT=2
RUN apt-get update && apt-get install -y --no-install-recommends \
    ghostscript qpdf tesseract-ocr tesseract-ocr-por tesseract-ocr-eng tesseract-ocr-spa \
    libreoffice-writer libreoffice-calc libreoffice-impress \
    fonts-dejavu-core fonts-liberation2 unpaper \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt 'ocrmypdf>=16.10,<18'
COPY backend ./backend
COPY frontend ./frontend
RUN groupadd --gid 10001 modupdf && useradd --uid 10001 --gid 10001 --no-create-home modupdf
USER modupdf
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8000","--workers","1","--no-access-log"]

FROM runtime AS test
USER root
COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
USER modupdf
CMD ["python","-m","pytest","-q","-p","no:cacheprovider"]

FROM runtime AS production
