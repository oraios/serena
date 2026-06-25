FROM ghcr.io/opentofu/opentofu:minimal AS tofu

FROM node:22.22-slim AS node

FROM serena:latest

USER root

COPY --from=node /usr/local /usr/local
COPY --from=tofu /usr/local/bin/tofu /usr/local/bin/tofu

RUN ln -s /usr/local/bin/tofu /usr/local/bin/terraform

USER serena