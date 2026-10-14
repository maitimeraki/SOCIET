# syntax=docker/dockerfile:1

# ---- build stage: compile the full dependency tree into wheels once ----------
FROM python:3.11-slim AS build
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt

# ---- runtime stage: slim, non-root, no build tools ---------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system app && useradd --system --gid app --no-create-home app
COPY --from=build /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY --chown=app:app src ./src
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./alembic.ini
USER app
EXPOSE 8000

# ---- api target: FastAPI + uvicorn -------------------------------------------
FROM runtime AS api
CMD ["uvicorn", "src.api.api_server:app", "--host", "0.0.0.0", "--port", "8000"]

# ---- worker target: RQ worker (same image, different entrypoint) -------------
FROM runtime AS worker
CMD ["python", "-m", "src.jobs.worker"]
