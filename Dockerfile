# Base stage with common dependencies
FROM python:3.11-slim AS base
SHELL ["/bin/bash", "-c"]

# Set environment variables to make Python print directly to the terminal and avoid .pyc files.
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies required for package manager and build tools.
# sudo, wget, zip needed for some assistants, like junie
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    ssh \
    sudo \
    wget \
    zip \
    unzip \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install pipx.
RUN python3 -m pip install --no-cache-dir pipx \
    && pipx ensurepath

# Install nodejs
ENV NVM_VERSION=0.40.3
ENV NODE_VERSION=22.18.0
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh | bash
# standard location
ENV NVM_DIR=/root/.nvm
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm use v${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm alias default v${NODE_VERSION}
ENV PATH="${NVM_DIR}/versions/node/v${NODE_VERSION}/bin/:${PATH}"

# Add local bin to the path
ENV PATH="${PATH}:/root/.local/bin"

# Install the latest version of uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Rust and rustup for rust-analyzer support (minimal profile)
ENV RUSTUP_HOME=/usr/local/rustup
ENV CARGO_HOME=/usr/local/cargo
ENV PATH="${CARGO_HOME}/bin:${PATH}"
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    --default-toolchain stable \
    --profile minimal \
    && rustup component add rust-analyzer

# Set the working directory
WORKDIR /workspaces/serena

# Copy all files for development
COPY . /workspaces/serena/

# Install sed
RUN apt-get update && apt-get install -y sed

# Create Serena configuration
ENV SERENA_HOME=/workspaces/serena/config
RUN mkdir -p $SERENA_HOME
RUN cp src/serena/resources/serena_config.template.yml $SERENA_HOME/serena_config.yml
RUN sed -i 's/^gui_log_window: .*/gui_log_window: False/' $SERENA_HOME/serena_config.yml
RUN sed -i 's/^web_dashboard_listen_address: .*/web_dashboard_listen_address: 0.0.0.0/' $SERENA_HOME/serena_config.yml
RUN sed -i 's/^web_dashboard_open_on_launch: .*/web_dashboard_open_on_launch: False/' $SERENA_HOME/serena_config.yml

# Create virtual environment and install dependencies
RUN uv venv
RUN . .venv/bin/activate
RUN uv pip install -r pyproject.toml -e .
ENV PATH="/workspaces/serena/.venv/bin:${PATH}"

# Entrypoint to ensure environment is activated
ENTRYPOINT ["/bin/bash", "-c", "source .venv/bin/activate && $0 $@"]
