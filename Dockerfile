# Base stage with common dependencies
FROM python:3.11-slim AS base
SHELL ["/bin/bash", "-c"]

# Set environment variables to make Python print directly to the terminal and avoid .pyc files.
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1

# Install system dependencies required for package manager and build tools.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    git \
    ssh \
    && rm -rf /var/lib/apt/lists/*

# Install pipx.
RUN python3 -m pip install --no-cache-dir pipx \
    && pipx ensurepath

# Add local bin to the path
ENV PATH="${PATH}:/root/.local/bin"

# Install the latest version of uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Set the working directory
WORKDIR /workspaces/serena

# Development target
FROM base AS development
# Copy all files for development
COPY . /workspaces/serena/

# Create virtual environment and install dependencies with dev extras
RUN uv venv
RUN . .venv/bin/activate
RUN uv pip install --all-extras -r pyproject.toml -e .
ENV PATH="/workspaces/serena/.venv/bin:${PATH}"

# Entrypoint to ensure environment is activated
ENTRYPOINT ["/bin/bash", "-c", "source .venv/bin/activate && $0 $@"]

# Production target
FROM base AS production
# Copy only necessary files for production
COPY pyproject.toml /workspaces/serena/
COPY README.md /workspaces/serena/
COPY src/ /workspaces/serena/src/

# Create virtual environment and install dependencies (production only)
RUN uv venv
RUN . .venv/bin/activate
RUN uv pip install -r pyproject.toml -e .
ENV PATH="/workspaces/serena/.venv/bin:${PATH}"

# Entrypoint to ensure environment is activated
ENTRYPOINT ["/bin/bash", "-c", "source .venv/bin/activate && $0 $@"]

