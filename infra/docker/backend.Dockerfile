FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false

RUN pip install --no-cache-dir poetry==1.8.3

COPY backend/pyproject.toml backend/poetry.lock* /app/
RUN poetry install --no-root --only main

COPY backend /app

EXPOSE 8000

# Shell form (not exec form) so $PORT is actually substituted at container
# start — Render injects a dynamic PORT and expects the process to bind it
# (staging audit §4). Falls back to 8000 for local `docker compose`, which
# never sets PORT.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
