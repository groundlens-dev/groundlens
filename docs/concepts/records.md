# Evidence records

Every verification ends in a **record**: a signed, hash-chained document that
captures the whole decision so someone else can check it later, offline, on any
machine, without calling GroundLens back.

## What a record holds

- the engine version;
- the input hash (the answer, sources and question, canonicalised);
- the full evidence graph — every verifier's evidence for every claim;
- the policy id and the policy hash;
- the decision, its reasons, and the regulatory mapping;
- a content hash, a record hash, the previous record's hash, and a signature
  with the signer's public key: Ed25519 by default, or ECDSA on P-256 when a
  key service signs (`signature_algorithm: ecdsa-p256-sha256`).

See {class}`groundlens.Record` and {class}`groundlens.RunRecord` for the fields.

## The content hash

`content_hash` covers everything that is a function of the input and the policy.
It is computed over canonical JSON, so **the same check gives the
same content hash on any machine**. The record id and timestamp are deliberately
left outside it: two verifications of the same input are two records with the
same content hash but different ids.

```{code-block} python
a = verify(answer, sources, question=q)
b = verify(answer, sources, question=q)
assert a.content_hash == b.content_hash     # same input + policy
assert a.record_id != b.record_id           # but two distinct records
```

## The chain

Append records to a JSON Lines log and each one carries the hash of the one
before it. That makes the log tamper-evident as a whole: editing a record
breaks its own content hash, and removing a record from the middle breaks the
next record's back-link.

```{code-block} python
from pathlib import Path
from groundlens import verify, Record

log = Path("records.jsonl")
for answer, sources in exchanges:
    verify(answer, sources, log=log)         # appends, chained to the previous

records = Record.read_log(log)
print(Record.verify_chain(records), "records, chain intact")
```

## Signing and attribution

Records are signed with Ed25519 by default. Set a stable key so records can be
attributed to your application; the public key travels inside every record, so
a verifier needs no key material from you. In production, sign with a key that
never leaves AWS KMS, Azure Key Vault or an HSM; see
[Sign and store records](../guides/sign-and-store.md).

```{code-block} bash
export GROUNDLENS_SIGNING_KEY="$(groundlens keygen)"
```

```{code-block} python
record = verify(answer, sources, signing_key=my_seed_hex)
```

## Verifying a record

```{code-block} python
record.verify()                     # recompute hashes and signature; raises if altered
Record.verify_chain(records)        # every hash, every link, every signature
```

```{code-block} bash
groundlens record verify records.jsonl
groundlens record verify records/            # several chains: every .jsonl in it
```

What an auditor can rely on: **integrity** (any change or reordering is detected
offline), **attribution** (each record is signed, the key is inside it),
**reproducibility** (same input and policy give the same content hash),
and **separation of duties** (the engine measured, the named-and-hashed policy
decided). To hand all of this to someone as a package, see
[Evidence for auditors](../guides/evidence-for-auditors.md).

## Records stay verifiable across releases

Records are kept for years, often longer than any one version of GroundLens
is in use. Every release therefore commits a set of records it wrote, signed
with a fixed test key, under `crates/gl-record/tests/fixtures/<version>/`. A
test in CI reads every one of those sets with the current code and checks that
each record still deserialises and that every signature and chain link still
verifies. A change that would break records users already keep fails the
build. When the record format changes, the schema name changes with it
(`groundlens.evidence-record/1` today) and the new code keeps a reader for the
old schema; the fixtures are never edited to make a test pass.
