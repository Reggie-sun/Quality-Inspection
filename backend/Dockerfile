FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml .
RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import subprocess, sys, tomllib; config = tomllib.load(open("pyproject.toml", "rb")); requirements = config["build-system"]["requires"] + config["project"]["dependencies"]; subprocess.check_call([sys.executable, "-m", "pip", "install", *requirements])'

COPY app ./app
RUN python -m pip install --no-cache-dir --no-deps --no-build-isolation .
COPY assets ./assets
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
