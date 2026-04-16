# Build context: the repository root (the demo programs in data/ are part of the
# image so the API can seed itself on an empty database).
#   docker build -f backend/Dockerfile -t npi-digital-twin-api .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# OR-Tools and SciPy ship manylinux wheels; no compiler toolchain is needed.
COPY backend/requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY data ./data

# Non-root runtime user
RUN useradd --create-home --uid 10001 npi && chown -R npi:npi /app
USER npi

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
