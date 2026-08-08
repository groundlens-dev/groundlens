"""Declarative rule-pack loading, validation and content hashing.

A rule pack is a YAML data file. It is never a Python module. This is the
whole point: a compliance reviewer who does not write Python has to be able
to read the pack, diff two versions of it, and sign off on the diff.

The loader is strict on purpose. An unknown ``assert`` value, an unknown key
or a missing required field is a hard load error with a file and line number,
never a warning and never a silent default. A pack that does not load cannot
be used, which is the only honest behaviour when the pack is the control.

The identity of a pack is :attr:`Pack.content_sha256`, the SHA-256 of the raw
file bytes taken *before* parsing. A version label is a string a human typed;
the content hash is what actually binds to behaviour, and it is what the audit
record stores.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

__all__ = [
    "ASSERT_KINDS",
    "SEVERITIES",
    "Pack",
    "PackError",
    "PackRule",
    "load_pack",
    "shipped_pack_names",
]


class PackError(ValueError):
    """A pack could not be read, parsed or validated.

    The message always names the offending file, and the line and key when
    the loader can determine them.
    """


ASSERT_KINDS: tuple[str, ...] = (
    "absent_lexicon",
    "all_facts_matched",
    "citations_resolve",
    "metadata_equals",
    "no_contradicted_facts",
    "obligation_polarity_consistent",
    "predicate",
    "present_lexicon",
)
"""The eight supported ``assert`` values. There are no others, and adding one
is a change to the frozen contract, not a change to a pack."""

SEVERITIES: tuple[str, ...] = ("info", "warn", "fail")
"""Allowed ``severity`` values, matching ``groundlens.types.Severity``."""

_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {"pack", "version", "locale_profile", "requires_metadata", "facts", "rules"}
)
_REQUIRED_TOP_LEVEL: tuple[str, ...] = ("pack", "version", "locale_profile", "rules")

_RULE_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "description",
        "assert",
        "severity",
        "where",
        "lexicon",
        "predicate",
        "key",
        "equals",
        "citation",
        "tags",
        "emit_on_pass",
    }
)
_REQUIRED_RULE_KEYS: tuple[str, ...] = ("id", "description", "assert", "severity")

_WHERE_KEYS: frozenset[str] = frozenset({"kind", "attrs"})

# Keys that each assert kind is allowed to carry beyond the common ones, and
# the keys it must carry. Anything outside this is rejected at load time, so a
# rule that looks like it filters or matches but silently does not cannot ship.
_ASSERT_ALLOWED: Mapping[str, frozenset[str]] = {
    "all_facts_matched": frozenset({"where"}),
    "no_contradicted_facts": frozenset({"where"}),
    "obligation_polarity_consistent": frozenset({"where"}),
    "citations_resolve": frozenset({"where"}),
    "absent_lexicon": frozenset({"lexicon"}),
    "present_lexicon": frozenset({"lexicon"}),
    "metadata_equals": frozenset({"key", "equals"}),
    "predicate": frozenset({"predicate"}),
}
_ASSERT_REQUIRED: Mapping[str, tuple[str, ...]] = {
    "all_facts_matched": (),
    "no_contradicted_facts": (),
    "obligation_polarity_consistent": (),
    "citations_resolve": (),
    "absent_lexicon": ("lexicon",),
    "present_lexicon": ("lexicon",),
    "metadata_equals": ("key", "equals"),
    "predicate": ("predicate",),
}

_COMMON_RULE_KEYS: frozenset[str] = frozenset(
    {"id", "description", "assert", "severity", "citation", "tags", "emit_on_pass"}
)


@dataclass(frozen=True, slots=True)
class PackRule:
    """One declarative rule.

    Attributes:
        id: Stable rule identifier, unique within the pack, surfaced in
            findings and in the audit record.
        description: One line of plain language. This is the text a
            compliance reviewer reads and approves.
        assertion: One of :data:`ASSERT_KINDS`. Spelled ``assert`` in YAML.
        severity: One of :data:`SEVERITIES`.
        where: Sorted key/value pairs selecting which facts the rule applies
            to. ``kind`` selects a fact kind; ``attrs`` is rendered as
            ``attr:<name>`` pairs.
        lexicon: Ordered phrases for the lexicon asserts.
        predicate: Dotted registry name, set only for ``assert: predicate``.
        key: Metadata key, set only for ``assert: metadata_equals``.
        equals: Expected metadata value as a string, set only for
            ``assert: metadata_equals``.
        citation: Free-text regulatory or academic provenance.
        tags: Sorted free-text tags. Carries the old rule sets' sub-score
            grouping across the port; has no effect on evaluation.
        emit_on_pass: When true, a passing rule emits ``rule.passed`` at
            severity INFO. Off by default so audit records stay small.
    """

    id: str
    description: str
    assertion: str
    severity: str
    where: tuple[tuple[str, str], ...] = ()
    lexicon: tuple[str, ...] = ()
    predicate: str | None = None
    key: str | None = None
    equals: str | None = None
    citation: str = ""
    tags: tuple[str, ...] = ()
    emit_on_pass: bool = False


@dataclass(frozen=True, slots=True)
class Pack:
    """A loaded, validated rule pack.

    Attributes:
        name: The ``pack:`` field.
        version: The ``version:`` field, a label. Not an identity; see
            :attr:`content_sha256`.
        locale_profile: Decimal separator, thousands separator and date order
            all come from here. Never from the environment.
        requires_metadata: Metadata keys that must be present in the mapping
            passed to ``check()``. Absence is a FAIL, always.
        facts_config: Sorted extractor configuration, all values normalised to
            strings so no float ever reaches the decision path.
        rules: The rules, in file order.
        content_sha256: SHA-256 over the raw file bytes, before parsing.
        source_path: Absolute path the pack was read from.
    """

    name: str
    version: str
    locale_profile: str
    requires_metadata: tuple[str, ...]
    facts_config: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    rules: tuple[PackRule, ...]
    content_sha256: str
    source_path: Path

    def facts_config_mapping(self) -> dict[str, dict[str, str]]:
        """Return :attr:`facts_config` as nested plain dicts for the extractor."""
        return {section: dict(entries) for section, entries in self.facts_config}

    def predicate_names(self) -> tuple[str, ...]:
        """Return the sorted, de-duplicated predicate names this pack references."""
        names = {rule.predicate for rule in self.rules if rule.predicate is not None}
        return tuple(sorted(names))


# ── Line mapping ────────────────────────────────────────────────────────────


def _line_map(text: str, source: Path) -> dict[tuple[str | int, ...], int]:
    """Map document paths to 1-based line numbers for error messages.

    Built from ``yaml.compose``, which constructs the node tree only and never
    instantiates Python objects, so it carries no deserialisation risk. The
    document itself is read with ``yaml.safe_load``.
    """
    try:
        node = yaml.compose(text, Loader=yaml.SafeLoader)
    except yaml.YAMLError:  # pragma: no cover - safe_load reports this first
        return {}
    out: dict[tuple[str | int, ...], int] = {}
    if node is not None:
        _walk_nodes(node, (), out)
    _ = source
    return out


def _walk_nodes(
    node: yaml.Node, path: tuple[str | int, ...], out: dict[tuple[str | int, ...], int]
) -> None:
    out.setdefault(path, node.start_mark.line + 1)
    if isinstance(node, yaml.MappingNode):
        for key_node, value_node in node.value:
            if not isinstance(key_node, yaml.ScalarNode):
                continue
            child = (*path, str(key_node.value))
            out[child] = key_node.start_mark.line + 1
            _walk_nodes(value_node, child, out)
    elif isinstance(node, yaml.SequenceNode):
        for index, item in enumerate(node.value):
            _walk_nodes(item, (*path, index), out)


class _Ctx:
    """Error-message context: where we are in the file, and on what line."""

    __slots__ = ("lines", "source")

    def __init__(self, source: Path, lines: dict[tuple[str | int, ...], int]) -> None:
        self.source = source
        self.lines = lines

    def fail(self, path: tuple[str | int, ...], message: str) -> PackError:
        line = self.lines.get(path)
        where = f"{self.source}:{line}" if line is not None else str(self.source)
        located = f"{where}: {message}"
        return PackError(located)


# ── Scalar coercion ─────────────────────────────────────────────────────────


def _as_config_scalar(value: object, ctx: _Ctx, path: tuple[str | int, ...]) -> str:
    """Coerce a YAML scalar to its canonical string form.

    Floats are rejected outright: contract section 5 forbids floating point
    anywhere in the decision path, and a tolerance written as ``0.01`` in YAML
    would arrive here as a binary float.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "null"
    if isinstance(value, float):
        msg = (
            f"value {value!r} is a floating-point number. Write it as a quoted "
            'decimal string instead, e.g. tolerance: "0.01". Floating point is '
            "not allowed anywhere in the decision path."
        )
        raise ctx.fail(path, msg)
    msg = f"expected a string, integer or boolean, got {type(value).__name__}"
    raise ctx.fail(path, msg)


def _as_str(value: object, ctx: _Ctx, path: tuple[str | int, ...], field: str) -> str:
    if not isinstance(value, str):
        msg = f"key {field!r} must be a string, got {type(value).__name__}"
        raise ctx.fail(path, msg)
    if not value.strip():
        msg = f"key {field!r} must not be empty"
        raise ctx.fail(path, msg)
    return value


def _as_str_list(
    value: object, ctx: _Ctx, path: tuple[str | int, ...], field: str
) -> tuple[str, ...]:
    if not isinstance(value, list):
        msg = f"key {field!r} must be a list of strings, got {type(value).__name__}"
        raise ctx.fail(path, msg)
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            msg = f"key {field!r}[{index}] must be a non-empty string"
            raise ctx.fail((*path, index), msg)
        out.append(item)
    return tuple(out)


def _as_mapping(
    value: object, ctx: _Ctx, path: tuple[str | int, ...], field: str
) -> dict[str, Any]:
    if not isinstance(value, dict):
        msg = f"key {field!r} must be a mapping, got {type(value).__name__}"
        raise ctx.fail(path, msg)
    for key in value:
        if not isinstance(key, str):
            msg = f"key {field!r} has a non-string key {key!r}"
            raise ctx.fail(path, msg)
    return dict(value)


def _reject_unknown(
    keys: Iterator[str] | Sequence[str],
    allowed: frozenset[str],
    ctx: _Ctx,
    path: tuple[str | int, ...],
    what: str,
) -> None:
    for key in keys:
        if key not in allowed:
            msg = f"unknown {what} key {key!r}. Allowed keys: {', '.join(sorted(allowed))}"
            raise ctx.fail((*path, key), msg)


# ── Rule parsing ────────────────────────────────────────────────────────────


def _parse_where(
    raw: object, ctx: _Ctx, path: tuple[str | int, ...]
) -> tuple[tuple[str, str], ...]:
    mapping = _as_mapping(raw, ctx, path, "where")
    _reject_unknown(list(mapping), _WHERE_KEYS, ctx, path, "where")
    pairs: list[tuple[str, str]] = []
    if "kind" in mapping:
        pairs.append(("kind", _as_str(mapping["kind"], ctx, (*path, "kind"), "kind")))
    if "attrs" in mapping:
        attrs = _as_mapping(mapping["attrs"], ctx, (*path, "attrs"), "attrs")
        for attr_key in sorted(attrs):
            attr_value = _as_config_scalar(attrs[attr_key], ctx, (*path, "attrs"))
            pairs.append((f"attr:{attr_key}", attr_value))
    if not pairs:
        msg = "key 'where' must select something; give it 'kind' and/or 'attrs'"
        raise ctx.fail(path, msg)
    return tuple(sorted(pairs))


def _parse_rule(raw: object, ctx: _Ctx, index: int) -> PackRule:
    path: tuple[str | int, ...] = ("rules", index)
    mapping = _as_mapping(raw, ctx, path, f"rules[{index}]")
    _reject_unknown(list(mapping), _RULE_KEYS, ctx, path, "rule")

    for required in _REQUIRED_RULE_KEYS:
        if required not in mapping:
            msg = f"rule at index {index} is missing required key {required!r}"
            raise ctx.fail(path, msg)

    rule_id = _as_str(mapping["id"], ctx, (*path, "id"), "id")
    description = _as_str(mapping["description"], ctx, (*path, "description"), "description")

    assertion = _as_str(mapping["assert"], ctx, (*path, "assert"), "assert")
    if assertion not in ASSERT_KINDS:
        msg = (
            f"rule {rule_id!r}: unknown assert value {assertion!r}. "
            f"Supported: {', '.join(ASSERT_KINDS)}"
        )
        raise ctx.fail((*path, "assert"), msg)

    severity = _as_str(mapping["severity"], ctx, (*path, "severity"), "severity")
    if severity not in SEVERITIES:
        msg = (
            f"rule {rule_id!r}: unknown severity {severity!r}. Supported: {', '.join(SEVERITIES)}"
        )
        raise ctx.fail((*path, "severity"), msg)

    allowed_here = _COMMON_RULE_KEYS | _ASSERT_ALLOWED[assertion]
    for key in mapping:
        if key not in allowed_here:
            msg = (
                f"rule {rule_id!r}: key {key!r} is not meaningful for "
                f"assert {assertion!r} and would be silently ignored"
            )
            raise ctx.fail((*path, key), msg)
    for required in _ASSERT_REQUIRED[assertion]:
        if required not in mapping:
            msg = f"rule {rule_id!r}: assert {assertion!r} requires key {required!r}"
            raise ctx.fail(path, msg)

    where: tuple[tuple[str, str], ...] = ()
    if "where" in mapping:
        where = _parse_where(mapping["where"], ctx, (*path, "where"))

    lexicon: tuple[str, ...] = ()
    if "lexicon" in mapping:
        lexicon = _as_str_list(mapping["lexicon"], ctx, (*path, "lexicon"), "lexicon")
        if not lexicon:
            msg = f"rule {rule_id!r}: 'lexicon' must contain at least one phrase"
            raise ctx.fail((*path, "lexicon"), msg)

    predicate: str | None = None
    if "predicate" in mapping:
        predicate = _as_str(mapping["predicate"], ctx, (*path, "predicate"), "predicate")

    metadata_key: str | None = None
    equals: str | None = None
    if "key" in mapping:
        metadata_key = _as_str(mapping["key"], ctx, (*path, "key"), "key")
    if "equals" in mapping:
        equals = _as_config_scalar(mapping["equals"], ctx, (*path, "equals"))

    citation = ""
    if "citation" in mapping:
        citation = _as_str(mapping["citation"], ctx, (*path, "citation"), "citation")

    tags: tuple[str, ...] = ()
    if "tags" in mapping:
        tags = tuple(sorted(_as_str_list(mapping["tags"], ctx, (*path, "tags"), "tags")))

    emit_on_pass = False
    if "emit_on_pass" in mapping:
        raw_flag = mapping["emit_on_pass"]
        if not isinstance(raw_flag, bool):
            msg = f"rule {rule_id!r}: 'emit_on_pass' must be true or false"
            raise ctx.fail((*path, "emit_on_pass"), msg)
        emit_on_pass = raw_flag

    return PackRule(
        id=rule_id,
        description=description,
        assertion=assertion,
        severity=severity,
        where=where,
        lexicon=lexicon,
        predicate=predicate,
        key=metadata_key,
        equals=equals,
        citation=citation,
        tags=tags,
        emit_on_pass=emit_on_pass,
    )


# ── Pack resolution and loading ─────────────────────────────────────────────


def _shipped_roots() -> tuple[Path, ...]:
    """Directories searched when ``load_pack`` is given a bare pack name.

    Two layouts are supported: the repository checkout (``<repo>/packs``) and
    an installed distribution that places the data next to the package
    (``groundlens/packs/data``). No environment variable participates: a pack
    that resolves differently on two machines is not a control.
    """
    here = Path(__file__).resolve()
    return (here.parents[3] / "packs", here.parent / "data")


def shipped_pack_names() -> tuple[str, ...]:
    """Return the sorted names of the packs that ship with the library."""
    names: set[str] = set()
    for root in _shipped_roots():
        if not root.is_dir():
            continue
        for child in root.iterdir():
            if (child / "pack.yaml").is_file():
                names.add(child.name)
    return tuple(sorted(names))


def _resolve(name_or_path: str | Path) -> Path:
    candidate = Path(name_or_path)
    looks_like_path = (
        isinstance(name_or_path, Path)
        or "/" in str(name_or_path)
        or "\\" in str(name_or_path)
        or str(name_or_path).endswith((".yaml", ".yml"))
    )
    if looks_like_path:
        resolved = candidate / "pack.yaml" if candidate.is_dir() else candidate
        if not resolved.is_file():
            msg = f"rule pack not found at {resolved}"
            raise PackError(msg)
        return resolved.resolve()

    name = str(name_or_path)
    for root in _shipped_roots():
        resolved = root / name / "pack.yaml"
        if resolved.is_file():
            return resolved.resolve()
    known = shipped_pack_names()
    msg = (
        f"unknown rule pack {name!r}. Shipped packs: "
        f"{', '.join(known) if known else '(none found)'}. "
        "Pass a path to load a pack from outside the library."
    )
    raise PackError(msg)


def load_pack(name_or_path: str | Path) -> Pack:
    """Load, validate and content-hash a rule pack.

    Args:
        name_or_path: A bare pack name resolved against the shipped ``packs/``
            directory, or a path to a ``pack.yaml`` or to the directory
            containing one.

    Returns:
        The validated :class:`Pack`.

    Raises:
        PackError: If the file is missing, is not valid YAML, or violates the
            schema. Every schema violation is an error; none is a warning.
    """
    path = _resolve(name_or_path)
    raw_bytes = path.read_bytes()
    content_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        msg = f"{path}: pack must be UTF-8 encoded ({exc})"
        raise PackError(msg) from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        msg = f"{path}: not valid YAML: {exc}"
        raise PackError(msg) from exc

    ctx = _Ctx(path, _line_map(text, path))

    if document is None:
        msg = f"{path}: pack file is empty"
        raise PackError(msg)
    if not isinstance(document, dict):
        msg = f"{path}: pack must be a mapping at the top level, got {type(document).__name__}"
        raise PackError(msg)

    _reject_unknown(list(document), _TOP_LEVEL_KEYS, ctx, (), "top-level")
    for required in _REQUIRED_TOP_LEVEL:
        if required not in document:
            msg = f"missing required top-level key {required!r}"
            raise ctx.fail((), msg)

    name = _as_str(document["pack"], ctx, ("pack",), "pack")
    version = _as_str(document["version"], ctx, ("version",), "version")
    locale_profile = _as_str(
        document["locale_profile"], ctx, ("locale_profile",), "locale_profile"
    )

    requires_metadata: tuple[str, ...] = ()
    if "requires_metadata" in document:
        requires_metadata = tuple(
            sorted(
                _as_str_list(
                    document["requires_metadata"],
                    ctx,
                    ("requires_metadata",),
                    "requires_metadata",
                )
            )
        )
        if len(set(requires_metadata)) != len(requires_metadata):
            msg = "'requires_metadata' contains duplicate keys"
            raise ctx.fail(("requires_metadata",), msg)

    facts_config: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = ()
    if "facts" in document:
        facts_raw = _as_mapping(document["facts"], ctx, ("facts",), "facts")
        sections: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        for section in sorted(facts_raw):
            entries = _as_mapping(facts_raw[section], ctx, ("facts", section), section)
            values = tuple(
                (entry_key, _as_config_scalar(entries[entry_key], ctx, ("facts", section)))
                for entry_key in sorted(entries)
            )
            sections.append((section, values))
        facts_config = tuple(sections)

    rules_raw = document["rules"]
    if not isinstance(rules_raw, list) or not rules_raw:
        msg = "'rules' must be a non-empty list"
        raise ctx.fail(("rules",), msg)

    rules = tuple(_parse_rule(raw, ctx, index) for index, raw in enumerate(rules_raw))

    seen: dict[str, int] = {}
    for index, rule in enumerate(rules):
        if rule.id in seen:
            msg = f"duplicate rule id {rule.id!r}, first defined at index {seen[rule.id]}"
            raise ctx.fail(("rules", index, "id"), msg)
        seen[rule.id] = index

    return Pack(
        name=name,
        version=version,
        locale_profile=locale_profile,
        requires_metadata=requires_metadata,
        facts_config=facts_config,
        rules=rules,
        content_sha256=content_sha256,
        source_path=path,
    )
