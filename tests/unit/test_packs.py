"""Tests for the declarative rule-pack system.

The loader tests run without ``groundlens.types``. The evaluation tests need
it and skip if the types module has not landed yet.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import inspect
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from groundlens.packs import predicates as predicates_module
from groundlens.packs.loader import (
    ASSERT_KINDS,
    SEVERITIES,
    PackError,
    load_pack,
    shipped_pack_names,
)
from groundlens.packs.predicates import PredicateError, PredicateRegistry

if TYPE_CHECKING:
    from groundlens.packs.predicates import PredicateContext

HAS_TYPES = importlib.util.find_spec("groundlens.types") is not None
requires_types = pytest.mark.skipif(
    not HAS_TYPES,
    reason="groundlens.types is written in parallel (CONTRACT.md section 2) and is not present",
)

MINIMAL_PACK = """\
pack: unit-test
version: 0.1.0
locale_profile: eu-es
rules:
  - id: R-001
    description: The answer must not promise a decision.
    assert: absent_lexicon
    lexicon: ["we have decided"]
    severity: fail
"""


def write_pack(tmp_path: Path, text: str, name: str = "pack.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ── Loading and identity ────────────────────────────────────────────────────


def test_loads_a_minimal_pack(tmp_path: Path) -> None:
    pack = load_pack(write_pack(tmp_path, MINIMAL_PACK))
    assert pack.name == "unit-test"
    assert pack.version == "0.1.0"
    assert pack.locale_profile == "eu-es"
    assert pack.requires_metadata == ()
    assert len(pack.rules) == 1
    assert pack.rules[0].assertion == "absent_lexicon"
    assert pack.rules[0].severity == "fail"
    assert pack.rules[0].lexicon == ("we have decided",)


def test_a_directory_resolves_to_its_pack_yaml(tmp_path: Path) -> None:
    write_pack(tmp_path, MINIMAL_PACK)
    assert load_pack(tmp_path).name == "unit-test"


def test_content_hash_is_over_the_raw_bytes(tmp_path: Path) -> None:
    path = write_pack(tmp_path, MINIMAL_PACK)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    assert load_pack(path).content_sha256 == expected


def test_content_hash_is_stable_across_loads(tmp_path: Path) -> None:
    path = write_pack(tmp_path, MINIMAL_PACK)
    assert load_pack(path).content_sha256 == load_pack(path).content_sha256


def test_a_comment_changes_the_hash_but_not_the_rules(tmp_path: Path) -> None:
    original = load_pack(write_pack(tmp_path, MINIMAL_PACK))
    commented = load_pack(
        write_pack(tmp_path, "# reviewed 2026-08-08\n" + MINIMAL_PACK, name="other.yaml")
    )
    assert commented.rules == original.rules
    assert commented.content_sha256 != original.content_sha256


def test_version_label_alone_does_not_identify_a_pack(tmp_path: Path) -> None:
    first = load_pack(write_pack(tmp_path, MINIMAL_PACK, name="a.yaml"))
    tampered = MINIMAL_PACK.replace("we have decided", "we have not decided")
    second = load_pack(write_pack(tmp_path, tampered, name="b.yaml"))
    assert first.version == second.version
    assert first.content_sha256 != second.content_sha256


def test_unknown_pack_name_names_the_shipped_packs() -> None:
    with pytest.raises(PackError, match="unknown rule pack"):
        load_pack("no-such-pack")


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(PackError, match="not found"):
        load_pack(tmp_path / "absent.yaml")


# ── Schema rejection ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param(
            MINIMAL_PACK + "extra_key: 1\n",
            "unknown top-level key 'extra_key'",
            id="unknown-top-level-key",
        ),
        pytest.param(
            MINIMAL_PACK.replace("locale_profile: eu-es\n", ""),
            "missing required top-level key 'locale_profile'",
            id="missing-locale-profile",
        ),
        pytest.param(
            MINIMAL_PACK.replace("pack: unit-test\n", ""),
            "missing required top-level key 'pack'",
            id="missing-pack-name",
        ),
        pytest.param(
            MINIMAL_PACK.replace("assert: absent_lexicon", "assert: vibes_ok"),
            "unknown assert value 'vibes_ok'",
            id="unknown-assert",
        ),
        pytest.param(
            MINIMAL_PACK.replace("assert: absent_lexicon", "assert: absentlexicon"),
            "unknown assert value",
            id="near-miss-assert",
        ),
        pytest.param(
            MINIMAL_PACK.replace("severity: fail", "severity: critical"),
            "unknown severity 'critical'",
            id="unknown-severity",
        ),
        pytest.param(
            MINIMAL_PACK.replace("    description: The answer must not promise a decision.\n", ""),
            "missing required key 'description'",
            id="missing-description",
        ),
        pytest.param(
            MINIMAL_PACK.replace("  - id: R-001\n    description:", "  - description:"),
            "missing required key 'id'",
            id="missing-id",
        ),
        pytest.param(
            MINIMAL_PACK.replace('    lexicon: ["we have decided"]\n', ""),
            "requires key 'lexicon'",
            id="assert-missing-its-key",
        ),
        pytest.param(
            MINIMAL_PACK + "    where: { kind: currency }\n",
            "not meaningful for assert 'absent_lexicon'",
            id="key-that-would-be-ignored",
        ),
        pytest.param(
            MINIMAL_PACK + "    sub_score: spec\n",
            "unknown rule key 'sub_score'",
            id="unknown-rule-key",
        ),
        pytest.param(
            MINIMAL_PACK + "    weight: 0.2\n",
            "unknown rule key 'weight'",
            id="weights-are-gone",
        ),
        pytest.param(
            'pack: p\nversion: "1"\nlocale_profile: eu-es\nrules: []\n',
            "must be a non-empty list",
            id="rules-empty-list",
        ),
        pytest.param(
            "pack: p\nversion: 1\nlocale_profile: eu-es\nrules: []\n",
            "key 'version' must be a string",
            id="unquoted-version-is-an-int",
        ),
        pytest.param(
            'pack: p\nversion: "1"\nlocale_profile: eu-es\nfacts:\n  currency:\n'
            "    tolerance: 0.01\nrules:\n  - id: A\n    description: d\n"
            "    assert: citations_resolve\n    severity: fail\n",
            "floating-point",
            id="float-in-facts-config",
        ),
        pytest.param(
            MINIMAL_PACK + MINIMAL_PACK.split("rules:\n")[1],
            "duplicate rule id 'R-001'",
            id="duplicate-rule-id",
        ),
        pytest.param(
            'pack: p\nversion: "1"\nlocale_profile: eu-es\nrules:\n  - id: A\n'
            "    description: d\n    assert: predicate\n    severity: fail\n",
            "requires key 'predicate'",
            id="predicate-without-a-name",
        ),
        pytest.param(
            'pack: p\nversion: "1"\nlocale_profile: eu-es\nrules:\n  - id: A\n'
            "    description: d\n    assert: metadata_equals\n    key: k\n"
            "    severity: fail\n",
            "requires key 'equals'",
            id="metadata-equals-without-a-value",
        ),
        pytest.param(
            'pack: p\nversion: "1"\nlocale_profile: eu-es\nrules:\n  - id: A\n'
            "    description: d\n    assert: all_facts_matched\n    severity: fail\n"
            "    where: { flavour: salty }\n",
            "unknown where key 'flavour'",
            id="unknown-where-key",
        ),
        pytest.param(
            "just a string\n",
            "must be a mapping at the top level",
            id="not-a-mapping",
        ),
        pytest.param("", "pack file is empty", id="empty-file"),
        pytest.param("pack: [\n", "not valid YAML", id="broken-yaml"),
    ],
)
def test_schema_violations_are_hard_errors(tmp_path: Path, mutation: str, expected: str) -> None:
    with pytest.raises(PackError) as excinfo:
        load_pack(write_pack(tmp_path, mutation))
    assert expected in str(excinfo.value)


def test_errors_carry_a_file_and_a_line(tmp_path: Path) -> None:
    path = write_pack(tmp_path, MINIMAL_PACK.replace("assert: absent_lexicon", "assert: nope"))
    with pytest.raises(PackError) as excinfo:
        load_pack(path)
    message = str(excinfo.value)
    assert str(path) in message
    assert f"{path}:7" in message, message


def test_a_schema_violation_is_never_a_warning(
    tmp_path: Path, recwarn: pytest.WarningsRecorder
) -> None:
    with pytest.raises(PackError):
        load_pack(write_pack(tmp_path, MINIMAL_PACK + "unknown: 1\n"))
    assert len(recwarn) == 0


# ── The eight assert kinds, and only those ──────────────────────────────────


def test_exactly_the_eight_contract_assert_kinds() -> None:
    assert set(ASSERT_KINDS) == {
        "all_facts_matched",
        "no_contradicted_facts",
        "absent_lexicon",
        "present_lexicon",
        "obligation_polarity_consistent",
        "citations_resolve",
        "metadata_equals",
        "predicate",
    }
    assert len(ASSERT_KINDS) == 8


def test_severities_match_the_contract() -> None:
    assert SEVERITIES == ("info", "warn", "fail")


# ── Fail closed, with no way out ────────────────────────────────────────────

_ESCAPE_WORDS = ("force", "skip", "disable")
_OWNED_MODULES = ("loader.py", "evaluate.py", "predicates.py")


def _parameter_names(source: str) -> list[str]:
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            args = node.args
            for arg in [
                *args.posonlyargs,
                *args.args,
                *args.kwonlyargs,
                args.vararg,
                args.kwarg,
            ]:
                if arg is not None:
                    names.append(arg.arg)
    return names


@pytest.mark.parametrize("filename", _OWNED_MODULES)
def test_no_parameter_can_switch_off_a_check(filename: str) -> None:
    """Fail-closed means fail-closed: no knob, anywhere, by any name."""
    path = Path(predicates_module.__file__).parent / filename
    for name in _parameter_names(path.read_text(encoding="utf-8")):
        for word in _ESCAPE_WORDS:
            assert word not in name.lower(), f"{filename} takes a parameter named {name!r}"


def test_control_has_no_escape_hatch_parameter_either() -> None:
    control_path = Path(predicates_module.__file__).parents[1] / "control.py"
    for name in _parameter_names(control_path.read_text(encoding="utf-8")):
        for word in _ESCAPE_WORDS:
            assert word not in name.lower(), f"control.py takes a parameter named {name!r}"


# ── Predicate registry ──────────────────────────────────────────────────────


def sample_predicate(ctx: PredicateContext) -> bool:
    """A predicate whose source this test hashes."""
    return bool(ctx.answer)


def test_registration_records_the_source_hash() -> None:
    registry = PredicateRegistry()
    registry.register("unit.sample", sample_predicate, description="sample")
    expected = hashlib.sha256(inspect.getsource(sample_predicate).encode("utf-8")).hexdigest()
    entry = registry.entry("unit.sample")
    assert entry.source_sha256 == expected
    assert entry.name == "unit.sample"
    assert entry.description == "sample"
    assert entry.func is sample_predicate


def test_a_source_change_changes_the_recorded_hash() -> None:
    def first(ctx: PredicateContext) -> bool:
        return True

    def second(ctx: PredicateContext) -> bool:
        return False

    registry = PredicateRegistry()
    registry.register("unit.first", first)
    registry.register("unit.second", second)
    assert (
        registry.entry("unit.first").source_sha256 != registry.entry("unit.second").source_sha256
    )


def test_registering_a_taken_name_is_an_error() -> None:
    registry = PredicateRegistry()
    registry.register("unit.sample", sample_predicate)
    with pytest.raises(PredicateError, match="already registered"):
        registry.register("unit.sample", sample_predicate)


def test_shipped_names_cannot_be_shadowed() -> None:
    with pytest.raises(PredicateError, match="already registered"):
        predicates_module.register("banking.disclosure_present", sample_predicate)


def test_an_unknown_predicate_is_an_error_not_a_pass() -> None:
    registry = PredicateRegistry()
    with pytest.raises(PredicateError, match="unknown predicate"):
        registry.get("unit.never_registered")


def test_names_must_be_dotted_lowercase() -> None:
    registry = PredicateRegistry()
    for bad in ("Banking.Thing", "nodots", "banking..thing", "banking.THING"):
        with pytest.raises(PredicateError, match="dotted lowercase"):
            registry.register(bad, sample_predicate)


def test_a_predicate_without_readable_source_is_refused() -> None:
    namespace: dict[str, Any] = {}
    exec("def dynamic(ctx):\n    return True\n", namespace)
    registry = PredicateRegistry()
    with pytest.raises(PredicateError, match="cannot read the source"):
        registry.register("unit.dynamic", namespace["dynamic"])


def test_registry_names_are_sorted() -> None:
    assert list(predicates_module.names()) == sorted(predicates_module.names())


# ── The shipped packs ───────────────────────────────────────────────────────


def test_both_ported_packs_ship() -> None:
    assert set(shipped_pack_names()) >= {"decision-rationale", "eu-retail-banking"}


@pytest.mark.parametrize("name", ["decision-rationale", "eu-retail-banking"])
def test_shipped_pack_loads_and_every_predicate_resolves(name: str) -> None:
    pack = load_pack(name)
    assert pack.name == name
    assert pack.rules
    for predicate_name in pack.predicate_names():
        assert predicates_module.entry(predicate_name).source_sha256


@pytest.mark.parametrize("name", ["decision-rationale", "eu-retail-banking"])
def test_shipped_rule_ids_are_unique_and_described(name: str) -> None:
    pack = load_pack(name)
    ids = [rule.id for rule in pack.rules]
    assert len(ids) == len(set(ids))
    for rule in pack.rules:
        assert rule.description.strip()
        assert rule.description.endswith(".")


def test_eu_retail_banking_matches_the_contract_example() -> None:
    pack = load_pack("eu-retail-banking")
    assert pack.version == "1.3.0"
    assert pack.locale_profile == "eu-es"
    assert pack.requires_metadata == ("disclosure_set", "product_type")
    assert pack.facts_config_mapping()["currency"]["tolerance"] == "0"
    assert pack.facts_config_mapping()["date"]["relative_requires_reference_date"] == "true"
    by_id = {rule.id: rule for rule in pack.rules}
    assert by_id["BNK-001"].assertion == "all_facts_matched"
    assert by_id["BNK-001"].where == (("kind", "currency"),)
    assert by_id["BNK-001"].citation == "EBA/GL/2020/06 §4.2"
    assert by_id["BNK-014"].assertion == "absent_lexicon"
    assert by_id["BNK-020"].assertion == "obligation_polarity_consistent"
    assert by_id["BNK-031"].predicate == "banking.disclosure_present"


def test_the_ported_legacy_rule_ids_survived() -> None:
    """The port keeps the old ids so two rule sets can be diffed."""
    banking = {rule.id for rule in load_pack("eu-retail-banking").rules}
    assert {"spec.reg_flag", "expl.causal", "bshift.length"} <= banking

    rationale = {rule.id for rule in load_pack("decision-rationale").rules}
    assert {"grnd.no_unsupported_extensions", "cal.self_consistency"} <= rationale
    # Dropped on purpose: it needs the user's question, which check() is not given.
    assert "comp.addresses_all_parts" not in rationale


def test_escape_hatch_ratio_is_what_the_handoff_claims() -> None:
    """If this fails, the reported adequacy of the format is wrong."""
    banking = load_pack("eu-retail-banking")
    rationale = load_pack("decision-rationale")
    # Select the ported rules by the tag that means "ported", not by the
    # absence of the "contract" tag. The pack now also carries native v2
    # grounding rules that are neither contract rules nor legacy ports, and
    # counting those as ports would misreport the adequacy of the format.
    ported_banking = [rule for rule in banking.rules if "legacy-banking-v1" in rule.tags]
    assert len(ported_banking) == 22
    assert sum(1 for rule in ported_banking if rule.assertion == "predicate") == 6
    assert len(rationale.rules) == 19
    assert sum(1 for rule in rationale.rules if rule.assertion == "predicate") == 8


# ── Evaluation ──────────────────────────────────────────────────────────────


@requires_types
def test_missing_metadata_is_a_fail_for_every_declared_key() -> None:
    from groundlens.packs.evaluate import missing_metadata_findings
    from groundlens.types import Severity

    pack = load_pack("eu-retail-banking")
    findings = missing_metadata_findings(pack, {})
    assert len(findings) == len(pack.requires_metadata) == 2
    assert {finding.code for finding in findings} == {"pack.metadata.missing"}
    assert all(finding.severity is Severity.FAIL for finding in findings)


@requires_types
@pytest.mark.parametrize("present", ["disclosure_set", "product_type"])
def test_each_missing_key_fails_on_its_own(present: str) -> None:
    from groundlens.packs.evaluate import missing_metadata_findings

    pack = load_pack("eu-retail-banking")
    findings = missing_metadata_findings(pack, {present: "x"})
    assert len(findings) == 1
    missing = next(key for key in pack.requires_metadata if key != present)
    assert missing in findings[0].message


@requires_types
def test_supplying_every_key_produces_no_metadata_finding() -> None:
    from groundlens.packs.evaluate import missing_metadata_findings

    pack = load_pack("eu-retail-banking")
    assert missing_metadata_findings(pack, dict.fromkeys(pack.requires_metadata, "x")) == ()


@requires_types
def test_a_none_value_still_counts_as_supplied() -> None:
    from groundlens.packs.evaluate import missing_metadata_findings

    pack = load_pack("eu-retail-banking")
    supplied = dict.fromkeys(pack.requires_metadata, None)
    assert missing_metadata_findings(pack, supplied) == ()


@requires_types
def test_lexicon_asserts(tmp_path: Path) -> None:
    from groundlens.packs.evaluate import evaluate_pack

    source = """\
pack: lex
version: "1"
locale_profile: eu-es
rules:
  - id: A
    description: No decision language.
    assert: absent_lexicon
    lexicon: ["we have decided", "we hereby grant"]
    severity: fail
  - id: B
    description: A disclaimer is present.
    assert: present_lexicon
    lexicon: ["not advice"]
    severity: warn
"""
    pack = load_pack(write_pack(tmp_path, source))
    findings = evaluate_pack(
        pack,
        answer="We Have Decided to proceed.",
        evidence=(),
        facts=(),
        matches=(),
        metadata={},
    )
    codes = sorted((finding.code, finding.rule_id) for finding in findings)
    assert codes == [("rule.failed", "A"), ("rule.failed", "B")]

    clean = evaluate_pack(
        pack,
        answer="This is not advice.",
        evidence=(),
        facts=(),
        matches=(),
        metadata={},
    )
    assert clean == ()


@requires_types
def test_metadata_equals_fails_closed_on_an_absent_key(tmp_path: Path) -> None:
    from groundlens.packs.evaluate import evaluate_pack
    from groundlens.types import Severity

    source = """\
pack: meta
version: "1"
locale_profile: eu-es
rules:
  - id: A
    description: The caller reports the injection screen ran.
    assert: metadata_equals
    key: injection_test_passed
    equals: "true"
    severity: fail
"""
    pack = load_pack(write_pack(tmp_path, source))
    absent = evaluate_pack(pack, answer="x", evidence=(), facts=(), matches=(), metadata={})
    assert [finding.code for finding in absent] == ["pack.metadata.missing"]
    assert absent[0].severity is Severity.FAIL

    wrong = evaluate_pack(
        pack,
        answer="x",
        evidence=(),
        facts=(),
        matches=(),
        metadata={"injection_test_passed": False},
    )
    assert [finding.code for finding in wrong] == ["rule.failed"]

    right = evaluate_pack(
        pack,
        answer="x",
        evidence=(),
        facts=(),
        matches=(),
        metadata={"injection_test_passed": True},
    )
    assert right == ()


@requires_types
def test_metadata_floats_are_refused(tmp_path: Path) -> None:
    from groundlens.packs.evaluate import evaluate_pack

    source = """\
pack: meta
version: "1"
locale_profile: eu-es
rules:
  - id: A
    description: Ratio must be one.
    assert: metadata_equals
    key: ratio
    equals: "1"
    severity: fail
"""
    pack = load_pack(write_pack(tmp_path, source))
    with pytest.raises(ValueError, match="floating-point"):
        evaluate_pack(pack, answer="x", evidence=(), facts=(), matches=(), metadata={"ratio": 1.0})


@requires_types
def test_an_unregistered_predicate_raises_instead_of_passing(tmp_path: Path) -> None:
    from groundlens.packs.evaluate import evaluate_pack

    source = """\
pack: pred
version: "1"
locale_profile: eu-es
rules:
  - id: A
    description: Something nobody implemented.
    assert: predicate
    predicate: nobody.implemented_this
    severity: fail
"""
    pack = load_pack(write_pack(tmp_path, source))
    with pytest.raises(PredicateError, match="unknown predicate"):
        evaluate_pack(pack, answer="x", evidence=(), facts=(), matches=(), metadata={})


@requires_types
def test_rule_passed_is_emitted_only_when_the_pack_asks(tmp_path: Path) -> None:
    from groundlens.packs.evaluate import evaluate_pack
    from groundlens.types import Severity

    source = """\
pack: pass
version: "1"
locale_profile: eu-es
rules:
  - id: QUIET
    description: Quiet rule.
    assert: present_lexicon
    lexicon: ["yes"]
    severity: warn
  - id: LOUD
    description: Loud rule.
    assert: present_lexicon
    lexicon: ["yes"]
    severity: warn
    emit_on_pass: true
"""
    pack = load_pack(write_pack(tmp_path, source))
    findings = evaluate_pack(pack, answer="yes", evidence=(), facts=(), matches=(), metadata={})
    assert [(finding.code, finding.rule_id) for finding in findings] == [("rule.passed", "LOUD")]
    assert findings[0].severity is Severity.INFO
