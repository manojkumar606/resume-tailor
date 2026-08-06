FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Requirements are copied on their own first so the (slow) install layer is
# cached and only rebuilds when dependencies actually change.
# No apt packages needed: psycopg[binary] and boto3 both ship manylinux wheels.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Never run the app as root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Migrations run at container start. Correct for a single instance, which is
# what the free plan gives; with several replicas booting at once this would
# race, and migrations should move to a dedicated pre-deploy step instead.
# `exec` replaces the shell so uvicorn receives SIGTERM directly and shuts down
# cleanly rather than being killed after a timeout.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
