# AgentCore Runtime requires linux/arm64.
#
# The image is the agents' toolchain: whatever a target repo's `test` commands need must be
# installed here. This general image covers Java 21 (Maven/Gradle wrappers), Node 22,
# Python 3.12 and Go. Add more (Rust, .NET, PHP...) with extra COPY/apt lines as you need.
FROM --platform=linux/arm64 node:22-bookworm-slim AS node
FROM --platform=linux/arm64 golang:1.23-bookworm AS go

FROM --platform=linux/arm64 eclipse-temurin:21-jdk-noble

COPY --from=ghcr.io/astral-sh/uv:0.11.2 /uv /usr/local/bin/uv
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=go /usr/local/go /usr/local/go
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && ln -s /usr/local/go/bin/go /usr/local/bin/go \
 && apt-get update \
 && apt-get install -y --no-install-recommends git make python3.12 python3.12-venv ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON=python3.12 UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

RUN useradd --create-home agent && mkdir -p /tmp/workspaces && chown agent /tmp/workspaces
USER agent
ENV WORKSPACE_ROOT=/tmp/workspaces

EXPOSE 8080
CMD ["/app/.venv/bin/python", "-m", "backlog_crew.app"]
