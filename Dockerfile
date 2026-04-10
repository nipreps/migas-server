FROM python:3.13-slim
ARG BUILDTYPE=test-latest
ARG DEPLOYSERVER=uvicorn
ARG VERSION="0.0.0dev"
ENV YARL_NO_EXTENSIONS=1 \
    MULTIDICT_NO_EXTENSIONS=1 \
    DEPLOYSERVER=${DEPLOYSERVER} \
    SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_CACHE=1 \
    PATH="/src/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Build uv sync flags from BUILDTYPE
RUN if [ "$BUILDTYPE" = "release" ]; then \
      echo "--locked --extra prod --no-dev" > /tmp/uv-flags; \
    elif [ "$BUILDTYPE" = "test" ]; then \
      echo "--locked --extra test" > /tmp/uv-flags; \
    else \
      echo "--extra test" > /tmp/uv-flags; \
    fi

# Install dependencies first (cached unless core metadata/lockfile changes)
WORKDIR /src/
COPY pyproject.toml uv.lock LICENSE README.md ./
RUN uv sync $(cat /tmp/uv-flags) --no-install-project

# Copy source and install the project
COPY . .
RUN uv sync $(cat /tmp/uv-flags)

# Install optional deploy server
RUN if [ "$DEPLOYSERVER" = "gunicorn" ]; then \
      uv pip install --no-cache gunicorn; \
    fi

RUN adduser --disabled-password --no-create-home appuser
USER appuser
WORKDIR /tmp
EXPOSE 8080

ENTRYPOINT ["/src/deploy/docker/run.sh"]
