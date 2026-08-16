# Pinned by digest so a clean checkout builds the same image everywhere.
FROM ghcr.io/astral-sh/uv:0.9.7@sha256:ba4857bf2a068e9bc0e64eed8563b065908a4cd6bfb66b531a9c424c8e25e142 AS uv

FROM python:3.13-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    MYPY_CACHE_DIR=/tmp/mypy \
    RUFF_CACHE_DIR=/tmp/ruff \
    PYTEST_ADDOPTS=-p\ no:cacheprovider

COPY --from=uv /uv /usr/local/bin/uv

WORKDIR /app

# Dependencies first, so editing the demo source does not re-resolve the locked environment.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

# The package metadata declares both, so the build needs them present.
COPY README.md LICENSE ./
COPY src ./src
RUN uv sync --locked

COPY tests ./tests
COPY scripts ./scripts
# The containment suite asserts against the real deployment definitions, so they ship with it.
COPY compose.yaml Dockerfile ./

# The demo runs unprivileged and keeps its disposable database outside the source tree.
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin demo \
    && mkdir -p /state \
    && chown demo:demo /state

USER demo

CMD ["uvicorn", "fieldblind.secure_app:create_secure_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
