FROM node:22.22-slim AS node
FROM rust:1.94-slim AS rust
FROM ghcr.io/astral-sh/uv:0.11.7 AS uv

FROM python:3.11-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SERENA_HOME=/home/serena/.serena

COPY ./src/serena/resources/serena_config.template.yml /home/serena/.serena/serena_config.yml

RUN sed -i 's/^gui_log_window: .*/gui_log_window: False/' "$SERENA_HOME/serena_config.yml" && \
    sed -i 's/^web_dashboard_listen_address: .*/web_dashboard_listen_address: 0.0.0.0/' "$SERENA_HOME/serena_config.yml" && \
    sed -i 's/^web_dashboard_open_on_launch: .*/web_dashboard_open_on_launch: False/' "$SERENA_HOME/serena_config.yml"

RUN useradd --create-home --shell /usr/sbin/nologin serena \
    && mkdir -p "/workspace" \
    && chown -R serena:serena "/workspace" \
    && chown -R serena:serena /home/serena

FROM base AS builder

WORKDIR /build

COPY --from=uv /uv /uvx /bin/

COPY pyproject.toml README.md uv.lock ./
COPY src ./src

RUN uv build

FROM base AS prod

WORKDIR /workspace

COPY --from=builder /build/dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -f /tmp/*.whl

USER serena

EXPOSE 9121 24282

ENTRYPOINT ["serena"]
CMD ["start-mcp-server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9121", "--project", "./"]

FROM base AS dev
SHELL ["/bin/bash", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    ssh \
    wget \
    zip \
    unzip \
    sed \
    && rm -rf /var/lib/apt/lists/*

# NVM can be re-added if switching node version is common while testing/developing serena
COPY --from=node /usr/local /usr/local
COPY --from=uv /uv /uvx /bin/
COPY --from=rust /usr/local/cargo /usr/local/cargo
COPY --from=rust /usr/local/rustup /usr/local/rustup

ENV CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    PATH="/usr/local/cargo/bin:${PATH}"

WORKDIR /workspaces/serena

COPY . /workspaces/serena/

RUN uv sync

ENV PATH="/workspaces/serena/.venv/bin:${PATH}"

ENTRYPOINT ["serena"]
CMD ["start-mcp-server", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9121", "--project", "./"]
