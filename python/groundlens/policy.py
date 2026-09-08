"""A policy is what your organisation considers acceptable. The engine has
no opinion; the policy does. It is YAML with a version and a hash, and the
hash goes into every record it decides."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from groundlens import _engine


class PolicyError(ValueError):
    """The policy did not pass lint. ``problems`` lists why."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("policy lint failed: " + "; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Policy:
    """A linted policy, ready to decide.

    >>> Policy.default().id
    'groundlens_default_v1'
    >>> Policy.load("policies/eu_ai_act_high_risk_v1.yaml").hash
    'sha256:...'
    """

    yaml: str
    id: str
    version: str
    hash: str

    @classmethod
    def from_yaml(cls, text: str) -> Policy:
        policy_hash, problems = _engine.policy_lint(text)
        if problems:
            raise PolicyError(problems)
        return cls(yaml=text, id=_field(text, "id"), version=_field(text, "version"), hash=policy_hash)

    @classmethod
    def load(cls, path: str | Path) -> Policy:
        return cls.from_yaml(Path(path).read_text(encoding="utf-8"))

    @classmethod
    def default(cls) -> Policy:
        """``groundlens_default_v1``: numeric contradictions fail, anything
        unresolved goes to review, no generative verifier decides."""
        return cls.from_yaml(_engine.default_policy_yaml())

    @classmethod
    def builtin(cls, name: str) -> Policy:
        """A policy shipped inside the package, e.g. ``eu_ai_act_high_risk_v1``."""
        if name == "groundlens_default_v1":
            return cls.default()
        text = resources.files("groundlens").joinpath("policies", f"{name}.yaml").read_text(encoding="utf-8")
        return cls.from_yaml(text)

    @classmethod
    def coerce(cls, value: Policy | str | Path | None) -> Policy:
        if value is None:
            return cls.default()
        if isinstance(value, Policy):
            return value
        if isinstance(value, Path):
            return cls.load(value)
        if "\n" not in value and Path(value).is_file():
            return cls.load(value)
        if "\n" in value:
            return cls.from_yaml(value)
        return cls.builtin(value)

    def lint(self) -> list[str]:
        return _engine.policy_lint(self.yaml)[1]


def _field(yaml_text: str, key: str) -> str:
    # Policies are hashed as canonical JSON in the engine; here we only need
    # two top-level scalars, and we refuse to add a YAML dependency for that.
    for line in yaml_text.splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip().strip("'\"")
    return ""
