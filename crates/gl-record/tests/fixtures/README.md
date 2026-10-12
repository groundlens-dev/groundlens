# Record compatibility fixtures

One directory per released version. Each holds records that version wrote,
signed with the test seed `4242…42` (32 bytes of `0x42`): a chain of two answer
records (`answer-records.jsonl`) and a run record (`run-records.jsonl`).
`tests/compat.rs` verifies every set with the current code.

To add the fixtures for a new release, from the repository root with that
release's `glv`:

    KEY=$(printf '42%.0s' {1..32}); D=crates/gl-record/tests/fixtures/<version>; mkdir -p "$D"
    glv verify --answer examples/invoice/answer.txt --source invoice.pdf#p1=examples/invoice/invoice.txt --question examples/invoice/question.txt --policy policies/eu_ai_act_high_risk_v1.yaml --rules rules/es_banking_v1.yaml --locale en --no-lexical --signing-key $KEY --log "$D/answer-records.jsonl"
    glv verify --answer examples/invoice/answer.txt --source invoice.pdf#p1=examples/invoice/invoice.txt --policy policies/eu_ai_act_high_risk_v1.yaml --locale en --no-lexical --signing-key $KEY --log "$D/answer-records.jsonl"
    glv run verify --trace examples/run/trace.jsonl --policy examples/run/execution-policy.yaml --run-id fixture-run-1 --system fixture --signing-key $KEY --log "$D/run-records.jsonl"

Never edit an existing fixture.
