# The Groundlens MCP server as a runnable image, for registries and sandboxes
# that want one. You do not need this to use the connector: install
# groundlens[encoder,mcp] and run python -m groundlens.mcp.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/groundlens/.cache/huggingface

WORKDIR /app

# CPU torch, explicitly and from its own index. The default wheel carries the
# CUDA runtime -- several gigabytes of it -- and nothing here touches a GPU.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY . /app
RUN pip install --no-cache-dir ".[encoder,mcp]"

RUN useradd --create-home --uid 10001 groundlens
USER groundlens

# The encoder is constructed on the first tool call, not at startup, so the
# server completes the handshake and answers tools/list with no model on disk
# and no network. The model (about 420 MB) downloads the first time it is used.
ENTRYPOINT ["python", "-m", "groundlens.mcp"]
