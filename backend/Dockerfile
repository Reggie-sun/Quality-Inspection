FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
COPY app ./app
RUN python -m pip install --no-cache-dir .
COPY assets ./assets
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
