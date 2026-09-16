FROM python:3.12-slim

WORKDIR /app

# System deps needed to build psycopg2 and friends
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD sh -c 'curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1'

# Runs migrations, then starts the server. Uses $PORT if the platform sets
# one (Railway, Render, etc. assign a dynamic port), otherwise falls back
# to 8000 for local `docker run` / docker-compose use.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
