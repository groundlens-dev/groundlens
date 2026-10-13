# Sign and store records

A record is only useful if it is still there, unchanged, when someone asks for
it, and if it can be traced to your application. This guide sets up both: a
key that signs every record, and a place that keeps them. Once both are set,
GroundLens stores each record **before** it returns the decision. If the
record cannot be stored, you get an error, not a decision.

## The short version

```{code-block} python
import boto3
import groundlens as gl

verifier = gl.Verifier(
    policy="eu_ai_act_high_risk_v1",
    signer=gl.signers.aws_kms(boto3.client("kms"), "alias/groundlens"),
    sink=gl.sinks.s3_object_lock(boto3.client("s3"), "my-audit-bucket", retain_days=3650),
)

record = verifier.check(
    question="What was UPS's 2023 revenue?",
    answer=answer,
    passages=[("10k#p114", passage, {"entity": "UPS"})],
    scope={"entity": "UPS"},
)
record.decision   # 'PASS' | 'REVIEW' | 'FAIL', and the record is already stored
```

You pass the clients you already use. GroundLens does not install `boto3`,
the Azure SDKs, `psycopg` or `python-pkcs11`, and it opens no connection of
its own.

## Who signs

| signer | where the key lives | for |
| --- | --- | --- |
| `gl.signers.local_key(seed)` | in your process | development, tests, a single machine |
| `gl.signers.aws_kms(client, key_id)` | AWS KMS, key spec `ECC_NIST_P256` | production on AWS |
| `gl.signers.azure_key_vault(crypto_client, key)` | Azure Key Vault or Managed HSM, `EC` key on `P-256` | production on Azure |
| `gl.signers.pkcs11(private_key, public_key)` | any HSM or token with a PKCS#11 driver | on-premises HSMs |

With a key service, the key never leaves it. GroundLens builds the record,
asks the service to sign the record's `record_hash`, checks the signature
against the service's public key, and only then returns the record. A wrong
key or a wrong signature is refused before any record exists.

Key services sign with ECDSA on the P-256 curve, so their records say
`"signature_algorithm": "ecdsa-p256-sha256"`. A record without that field is
Ed25519, like every record written before key services were supported. Both
verify offline with `groundlens record verify`, from the public key inside the
record.

A local key is a 32-byte seed. Keep it in a secret manager; whoever can read
it can sign as you. Without any signer, every record is signed with a new key:
the record still proves it was not changed, but not who wrote it.

## Where records go

| sink | what it writes | what keeps it from changing |
| --- | --- | --- |
| `gl.sinks.jsonl(path)` | one line per record in a file, fsynced on every write | file permissions; copy it somewhere safe |
| `gl.sinks.s3_object_lock(client, bucket, retain_days=…)` | one object per record | S3 Object Lock retention (`COMPLIANCE` by default) |
| `gl.sinks.azure_blob(container_client)` | one blob per record | the container's immutability policy |
| `gl.sinks.postgres(connection)` | one row per record | database permissions; the table refuses a second record at the same position or a fork |

Each sink keeps one **chain**: every record names the hash of the one before
it. A position in the chain is written once: S3 writes with `If-None-Match`,
Azure with `overwrite=False`, Postgres has `(chain, position)` as its primary
key and `previous_record_hash` unique per chain. If two writers race for the
same position, the second one is told, and `check` reads the new head and
seals again.

## Many processes

Give each process its own chain, and verify all of them together:

```{code-block} python
sink = gl.sinks.jsonl("records/", chain=f"worker-{worker_id}")
```

```{code-block} bash
groundlens record verify records/          # every .jsonl in the directory
groundlens record verify a.jsonl b.jsonl   # or name them
```

Every chain must verify on its own, and the same record may not appear in two
chains.

## Writing in batches

`check` stores one record at a time. A batch writer can seal first and store
afterwards; the record is not a decision until it is stored.

```{code-block} python
record = verifier.seal(answer=a, passages=p, previous=sink.head())
verifier.store(record)
```

## What a record proves, and what it does not

A signature proves the record was not changed after it was signed, and which
key signed it. It does not prove that the key belongs to you: an auditor needs
your public key from you, through a channel they trust, and compares it with
the one in the records. It does not prove the log is complete either; a
chain shows a record missing from the middle, but not one missing from the
end. Object Lock, immutable containers and database permissions are what keep
the end of the chain where it was.
