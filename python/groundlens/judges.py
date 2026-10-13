# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The judge: the model you already use, asked a fixed question.

GroundLens ships no model. You pass the client you already have, and
GroundLens sends it one fixed, versioned prompt per answer, with the policy,
the scope and the provenance of every passage. The judge labels each sentence
of the answer ``supported``, ``unsupported``, ``contradicted`` or
``uncertain``, citing passages. It never decides: the policy's ``judge``
section says what its labels may do, and by default they can only send an
answer to review. A timeout, an error or a reply that is not the JSON asked
for is review too, never a pass.

- :func:`openai_compatible`: any client with the OpenAI chat API: OpenAI,
  vLLM, Ollama, LiteLLM, your own gateway.
- :func:`azure_openai`: an ``openai.AzureOpenAI`` client and a deployment.
- :func:`bedrock`: a ``boto3.client("bedrock-runtime")`` and a model id.

The record keeps the template id, the hash of the exact prompt, the model the
provider says answered and the hash of its raw reply. ``groundlens judge
show-template`` prints the exact prompt for a given input.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Judge(Protocol):
    """Anything that can send a system and a user message to a model.

    ``complete`` returns the reply text and the model the provider says
    answered. It may raise; GroundLens records the error and the answer goes
    to review.
    """

    adapter: str
    model: str

    def complete(self, system: str, user: str) -> tuple[str, str]: ...


class OpenAICompatible:
    adapter = "openai_compatible"

    def __init__(self, client: Any, model: str, *, timeout: float = 60.0, json_mode: bool = True) -> None:
        self.client = client
        self.model = model
        self.timeout = timeout
        self.json_mode = json_mode

    def complete(self, system: str, user: str) -> tuple[str, str]:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0,
            "timeout": self.timeout,
        }
        if self.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        reply = self.client.chat.completions.create(**kwargs)
        return reply.choices[0].message.content or "", getattr(reply, "model", None) or self.model


def openai_compatible(client: Any, model: str, *, timeout: float = 60.0, json_mode: bool = True) -> OpenAICompatible:
    """A judge on any OpenAI-compatible endpoint. ``client`` is an
    ``openai.OpenAI`` (or compatible) client; point its ``base_url`` at vLLM or
    Ollama to keep everything on your own servers. Set ``json_mode=False`` for
    servers that do not support ``response_format``."""
    return OpenAICompatible(client, model, timeout=timeout, json_mode=json_mode)


class AzureOpenAI(OpenAICompatible):
    adapter = "azure_openai"


def azure_openai(client: Any, deployment: str, *, timeout: float = 60.0) -> AzureOpenAI:
    """A judge on Azure OpenAI. ``client`` is an ``openai.AzureOpenAI``;
    ``deployment`` is your deployment name."""
    return AzureOpenAI(client, deployment, timeout=timeout)


class Bedrock:
    adapter = "bedrock"

    def __init__(self, client: Any, model_id: str, *, max_tokens: int = 2048) -> None:
        self.client = client
        self.model = model_id
        self.max_tokens = max_tokens

    def complete(self, system: str, user: str) -> tuple[str, str]:
        reply = self.client.converse(
            modelId=self.model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"temperature": 0, "maxTokens": self.max_tokens},
        )
        parts = reply["output"]["message"]["content"]
        return "".join(p.get("text", "") for p in parts), self.model


def bedrock(client: Any, model_id: str, *, max_tokens: int = 2048) -> Bedrock:
    """A judge on AWS Bedrock, through the Converse API. ``client`` is
    ``boto3.client("bedrock-runtime")``. Set the client's read timeout in its
    ``botocore.config.Config``."""
    return Bedrock(client, model_id, max_tokens=max_tokens)


def ask(judge: Judge, prompt: dict[str, Any]) -> dict[str, Any]:
    """Send a rendered prompt to a judge and shape the reply for the engine.
    Never raises: an error becomes part of the reply, and the policy sends the
    answer to review."""
    try:
        text, model = judge.complete(prompt["system"], prompt["user"])
        return {"adapter": judge.adapter, "model": model or judge.model, "response": text, "error": None}
    except Exception as e:  # noqa: BLE001 - whatever the client raises, the answer must not pass
        return {"adapter": judge.adapter, "model": judge.model, "response": None, "error": f"{type(e).__name__}: {e}"[:500]}
