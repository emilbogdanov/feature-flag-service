# syntax=docker/dockerfile:1
# Built from the repository root, because the server installs the SDK from ../sdk:
#   docker build -f backend/Dockerfile -t flagstaff-server .

ARG PYTHON_IMAGE=python:3.13-slim-trixie

FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
# Bytecode is compiled once here rather than on every start. Files are copied out of the cache,
# not linked, because the cache mount isn't part of the image.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/flagstaff
WORKDIR /src/backend
# The dependencies get a layer of their own, so a change to the server alone doesn't reinstall
# them. The SDK is one of them, installed as a regular package rather than linked to /src.
COPY sdk /src/sdk
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --no-install-project
COPY backend ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM ${PYTHON_IMAGE}
RUN groupadd --system --gid 10001 flagstaff \
    && useradd --system --uid 10001 --gid flagstaff --no-create-home --shell /usr/sbin/nologin flagstaff
COPY --from=build /opt/flagstaff /opt/flagstaff
# Migrations run from here: docker compose run --rm api alembic upgrade head
WORKDIR /app
COPY --from=build /src/backend/alembic.ini ./
COPY --from=build /src/backend/migrations ./migrations
ENV PATH=/opt/flagstaff/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
USER flagstaff
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
# One server process per container. Scale by running more containers: the metrics and the SDK
# stream fan-out are both per process.
CMD ["flagstaff-server", "serve", "--host", "0.0.0.0", "--port", "8000"]
