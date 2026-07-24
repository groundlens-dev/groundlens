# Data Handling & Privacy

Groundlens is a client-side Python library. It has no server, no account, and no telemetry in the scoring path. This page states what the library does and does not do with your data, and how you can verify each claim yourself. The canonical, versioned statement lives in [`DATA_HANDLING.md`](https://github.com/groundlens-dev/groundlens/blob/main/DATA_HANDLING.md) at the repository root.

## What stays on your machine

The deterministic core (SGI, DGI, rules) and the `check()` renderer run entirely in your process. They compute embeddings and geometry locally and return a result. Nothing about your questions, sources, or answers is sent anywhere.

Local scoring sends nothing out. There is no Groundlens endpoint in the path, because Groundlens holds no API key of its own and runs no server. This is a structural property, not a promise: the core scoring path imports no HTTP client and no socket.

The only thing Groundlens writes to disk is the audit log, and only when you open one yourself with `groundlens.audit.open_log(path)`. It is a local SQLite file at a path you choose, on your infrastructure.

## What leaves your machine, and only then

1. **Model download, one time.** On first use, the embedding model (and, for the optional consistency checks, a local generation model and NLI model) is downloaded from Hugging Face and cached locally. This is inbound: the model comes to you, your questions and answers are not uploaded. After the download, scoring runs offline.

2. **A hosted API provider, only if you configure one.** If you run the second-stage consistency check against a hosted model through `AnthropicGenerator`, `OpenAIGenerator`, or `GeminiGenerator`, your prompt and the model's answer go to **that provider**, using **your** API key, under **that provider's** terms. Groundlens sends them nowhere else. With a local model instead, the second stage also sends nothing out.

## Verify it yourself

- **No-egress test (runs in CI):** `tests/unit/test_no_egress.py` blocks every socket connection, then scores with an in-memory encoder. If any part of local scoring tried to reach the network, the test fails. It passes, and it is reproducible.
- **Under a network monitor:** run your scoring under `tcpdump` or in a no-egress container. During local scoring, after the one-time model download, there are zero outbound connections. With an API generator, the only traffic is to the endpoint you configured.
- **Read the source:** the library is open source (Apache-2.0). The core scoring path imports no HTTP client (`requests`, `urllib`, `httpx`) and no `socket`, so you can confirm there is no telemetry or exfiltration.

## Fully offline / air-gapped operation

1. Pre-download your encoder on a connected machine, or supply your own via `encoder=` / `set_default_encoder(...)`. The custom-encoder path never imports `sentence-transformers`.
2. Set `HF_HUB_OFFLINE=1` (and `TRANSFORMERS_OFFLINE=1` if you use the local consistency checks).
3. Score. SGI, DGI, and rules run with no network at all.

## See also

- [`DATA_HANDLING.md`](https://github.com/groundlens-dev/groundlens/blob/main/DATA_HANDLING.md) at the repository root: the canonical statement.
- [Second stage (model-based)](second-stage.md): when and how a hosted provider enters the path.
- [Custom Encoders / No-Torch](custom-encoders.md): supplying your own encoder for air-gapped use.
