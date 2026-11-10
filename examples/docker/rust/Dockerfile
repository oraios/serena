FROM rust:1.94-slim AS rust

FROM ghcr.io/oraios/serena:latest

USER root

# C toolchain for build scripts and proc macros
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=rust /usr/local/cargo /usr/local/cargo
COPY --from=rust /usr/local/rustup /usr/local/rustup

ENV RUSTUP_HOME=/usr/local/rustup \
    PATH="/usr/local/cargo/bin:${PATH}"

# installed at build time, since the toolchain is not writable for the runtime user
RUN CARGO_HOME=/usr/local/cargo rustup component add rust-analyzer rust-src

USER serena

# writable location for the cargo registry and build cache
ENV CARGO_HOME=/home/serena/.cargo
