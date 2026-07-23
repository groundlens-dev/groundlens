# Data handling and privacy

Groundlens is a client-side Python library. It has no server, no account, and no
telemetry. This document states exactly what it does and does not do with your
data, and how you can verify each claim yourself.

## What stays on your machine

The deterministic core (SGI, DGI, rules) and the `check()` renderer run entirely
in your process. They compute embeddings and geometry locally and return a
result. Nothing about your questions, sources, or answers is sent anywhere.

The only thing Groundlens writes to disk is the **audit log**, and only when you
open one yourself with `groundlens.audit.open_log(path)`. It is a local SQLite
file at a path you choose, on your infrastructure. Groundlens writes nothing else
to disk and keeps no hidden state.

## What leaves your machine, and only then

1. **Model download (one time).** On first use, the embedding model (and, for the
   optional consistency checks, a local generation model and NLI model) is
   downloaded from Hugging Face and cached locally. This is inbound: the model
   comes to you. Your questions and answers are not uploaded. After the download,
   scoring runs offline. Set `HF_HUB_OFFLINE=1` with a pre-fetched model to run
   fully air-gapped, or supply your own encoder (the custom-encoder path never
   imports sentence-transformers).

2. **An API generator or provider, only if you configure one.** If you choose to
   run the consistency checks against Claude, GPT, Gemini, or an OpenAI-compatible
   endpoint (`groundlens.verify.AnthropicGenerator` / `OpenAIGenerator` /
   `GeminiGenerator`), your prompts and the model's answers are sent to **that
   provider**, using **your** API key, under **that provider's** data terms.
   Groundlens sends them nowhere else.

## We have no access to your data

This is structural, not a promise:

- Groundlens has **no server and no account** in the path. There is no Groundlens
  endpoint that your data passes through.
- API calls are made **directly from your machine to the provider you chose**,
  authenticated with **your** key. Groundlens holds no key of its own.
- The library is **open source (Apache-2.0)**. You can read every line and
  confirm there is no telemetry, analytics, or exfiltration: the core imports no
  HTTP client (`requests`, `urllib`, `httpx`), no `socket`, and no analytics SDK.

## Verify it yourself

- **No-egress test (runs in CI):** `tests/unit/test_no_egress.py` blocks every
  socket connection, then scores with an in-memory encoder. If any part of local
  scoring tried to reach the network, the test fails. It passes.
- **Under a network monitor:** run your scoring under `tcpdump` or in a
  no-egress container. During local scoring (after the one-time model download)
  there are zero outbound connections. With an API generator, the only traffic is
  to the endpoint you configured.
- **Read the source:** the core scoring path imports no HTTP client or socket.
  Confirm with an import-anchored search (returns nothing):
  `grep -rnE "^[[:space:]]*(import|from) .*(requests|httpx|urllib|socket|http\.client)" src/groundlens/`

## Fully offline / air-gapped operation

1. Pre-download your encoder on a connected machine, or supply your own via
   `encoder=` / `set_default_encoder(...)`.
2. Set `HF_HUB_OFFLINE=1` (and `TRANSFORMERS_OFFLINE=1` if you use the local
   consistency checks).
3. Score. SGI, DGI, and rules run with no network at all.
