FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium

COPY . .

# instance/ (SQLite DB) and logs/ are gitignored runtime state, not part of the
# image; mount volumes over them to persist data across container recreation.
RUN mkdir -p instance logs \
    && useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app /opt/playwright-browsers
USER appuser

EXPOSE 5000

# SECRET_KEY, ALLOWED_ORIGIN, FLASK_DEBUG, LOG_LEVEL are read from the
# environment at startup (see README) — pass them via `docker run -e` /
# `--env-file` / compose, not baked into the image.
CMD ["python", "app.py"]
