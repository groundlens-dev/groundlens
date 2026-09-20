# Evidence records

Every verification ends in a **record**: a signed, hash-chained document that
captures the whole decision so someone else can check it later, offline, on any
machine, without calling GroundLens back.

## What a record holds

- the engine version and the bundle hash (which models, by hash, took part);
- the input hash (the answer, sources and question, canonicalised);
- the full evidence graph — every verifier's evidence for every claim;
- the policy id and the policy hash;
- the decision, its reasons, and the regulatory mapping;
- a content hash, a record hash, the previous record's hash, and an Ed25519
  signature with the signer's public key.

See {class}`groundlens.Record` and {class}`groundlens.RunRecord` for the fields.

## The content hash

`content_hash` covers everything that is a function of the input, the policy and
the bundle. It is computed over canonical JSON, so **the same check gives the
same content hash on any machine**. The record id and timestamp are deliberately
left outside it: two verifications of the same input are two records with the
same content hash but different ids.

```{code-block} python
a = verify(answer, sources, question=q)
b = verify(answer, sources, question=q)
assert a.content_hash == b.content_hash     # same input + policy + bundle
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

Records are signed with Ed25519. Set a stable key so records can be attributed
to your application; the public key travels inside every record, so a verifier
needs no key material from you.

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
```

What an auditor can rely on: **integrity** (any change or reordering is detected
offline), **attribution** (each record is signed, the key is inside it),
**reproducibility** (same input, policy and bundle give the same content hash),
and **separation of duties** (the engine measured, the named-and-hashed policy
decided). To hand all of this to someone as a package, see
[Evidence for auditors](../guides/evidence-for-auditors.md).
