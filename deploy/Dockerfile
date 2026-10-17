# syntax=docker/dockerfile:1.7
# Knockout API. Build from the repository root:
#   docker build -f deploy/Dockerfile -t knockout-api .

FROM python:3.14.8-slim-trixie AS build

# git fetches the pinned Helix dependency
RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv

WORKDIR /app

# Dependencies first, against a placeholder package and readme, so source and doc edits reuse this layer.
# The API packages are listed here as well as in any "api" extra, so the image works either way.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p src/knockout \
    && touch src/knockout/__init__.py README.md \
    && pip install --editable ".[api]" \
       "fastapi>=0.142" "uvicorn[standard]>=0.54" "sentry-sdk[fastapi]>=2.40" "psycopg[binary]>=3.2"

COPY src ./src
RUN pip install --no-deps --editable . \
    && knockout setup

# Committed mappings (data/mappings), benchmark scripts and anything else the context allows
COPY . .


FROM python:3.14.8-slim-trixie

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --uid 10001 knockout

COPY --from=build /opt/venv /opt/venv
COPY --from=build --chown=knockout:knockout /app /app

WORKDIR /app
USER knockout
RUN mkdir -p data/cache data/store data/reports data/mappings

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# Workers follow WEB_CONCURRENCY (default 1, which the file store expects)
CMD ["uvicorn", "knockout.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
