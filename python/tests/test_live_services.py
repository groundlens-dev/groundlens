# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""The sinks and signers against the real software, not stand-ins.

Each test runs only when its service is reachable, named by an environment
variable; otherwise it is skipped. CI starts them all (``live-services`` in
``.github/workflows/ci.yml``):

- ``GL_LIVE_POSTGRES``: a libpq connection URL to a Postgres you can create tables in
- ``GL_LIVE_S3``: an S3 endpoint with Object Lock (MinIO), user and password in
  ``GL_LIVE_S3_USER`` and ``GL_LIVE_S3_PASSWORD``
- ``GL_LIVE_KMS``: an AWS KMS endpoint (LocalStack)
- ``GL_LIVE_AZURE_BLOB``: an Azure Blob endpoint (Azurite), the emulator's well-known account
- ``GL_LIVE_PKCS11``: the path of a PKCS#11 module (SoftHSM 2); a fresh token is made

Azure Key Vault has no emulator and is not tested here.
"""

from __future__ import annotations

import os
import subprocess
import uuid

import groundlens as gl
import pytest
from groundlens.record import Record
from groundlens.sinks import ChainConflict

ANSWER = "Revenue was €10M."
PASSAGES = [("10k#p1", "Revenue was €10M.")]


def service(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


def a_chain_of_three(sink, signer=None) -> list[Record]:
    v = gl.Verifier(signer=signer or gl.signers.local_key(), sink=sink)
    records = [v.check(answer=ANSWER, passages=PASSAGES) for _ in range(3)]
    back = sink.records()
    assert [r.record_hash for r in back] == [r.record_hash for r in records]
    assert Record.verify_chain(back) == 3
    return records


def a_second_writer_loses(sink) -> None:
    """A writer that read the head before the last append cannot write."""
    stale = gl.Verifier().seal(answer=ANSWER, passages=PASSAGES, previous=None)
    with pytest.raises(ChainConflict):
        sink.append(stale)


def test_postgres():
    psycopg = pytest.importorskip("psycopg")
    conn = psycopg.connect(service("GL_LIVE_POSTGRES"))
    table = f"gl_{uuid.uuid4().hex[:12]}"
    sink = gl.sinks.postgres(conn, table=table)
    records = a_chain_of_three(sink)
    a_second_writer_loses(sink)
    # The table itself refuses a fork, whoever writes to it.
    with pytest.raises(psycopg.errors.UniqueViolation), conn.transaction():
        conn.execute(
            f"INSERT INTO {table} VALUES ('records', 9, 'x', 'sha256:x', %s, '{{}}')",
            (records[0].record_hash,),
        )


def s3_client():
    boto3 = pytest.importorskip("boto3")
    return boto3.client(
        "s3",
        endpoint_url=service("GL_LIVE_S3"),
        aws_access_key_id=service("GL_LIVE_S3_USER"),
        aws_secret_access_key=service("GL_LIVE_S3_PASSWORD"),
        region_name="us-east-1",
    )


def test_s3_object_lock():
    s3 = s3_client()
    bucket = f"gl-{uuid.uuid4().hex[:12]}"
    s3.create_bucket(Bucket=bucket, ObjectLockEnabledForBucket=True)
    sink = gl.sinks.s3_object_lock(s3, bucket, retain_days=1)
    a_chain_of_three(sink)
    a_second_writer_loses(sink)

    key = "groundlens/records/000000000000.json"
    head = s3.head_object(Bucket=bucket, Key=key)
    assert head["ObjectLockMode"] == "COMPLIANCE"
    # Under COMPLIANCE retention the record cannot be deleted, not even by root.
    version = head["VersionId"]
    with pytest.raises(Exception, match="AccessDenied|locked|retention|WORM"):
        s3.delete_object(Bucket=bucket, Key=key, VersionId=version)


def test_aws_kms_signs_records_that_verify_offline(tmp_path):
    boto3 = pytest.importorskip("boto3")
    kms = boto3.client(
        "kms",
        endpoint_url=service("GL_LIVE_KMS"),
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1",
    )
    key = kms.create_key(KeySpec="ECC_NIST_P256", KeyUsage="SIGN_VERIFY")["KeyMetadata"]["KeyId"]
    signer = gl.signers.aws_kms(kms, key)
    records = a_chain_of_three(gl.sinks.jsonl(tmp_path), signer)
    assert all(r.raw["signature_algorithm"] == "ecdsa-p256-sha256" for r in records)

    other = kms.create_key(KeySpec="RSA_2048", KeyUsage="SIGN_VERIFY")["KeyMetadata"]["KeyId"]
    with pytest.raises(ValueError, match="ECC_NIST_P256"):
        gl.signers.aws_kms(kms, other).public_key()


def test_azure_blob():
    blob = pytest.importorskip("azure.storage.blob")
    endpoint = service("GL_LIVE_AZURE_BLOB")
    # Azurite's well-known development account.
    account = "devstoreaccount1"
    secret = "Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="
    conn = f"DefaultEndpointsProtocol=http;AccountName={account};AccountKey={secret};BlobEndpoint={endpoint}/{account};"
    container = blob.BlobServiceClient.from_connection_string(conn).create_container(f"gl-{uuid.uuid4().hex[:12]}")
    sink = gl.sinks.azure_blob(container)
    a_chain_of_three(sink)
    a_second_writer_loses(sink)


def test_pkcs11_softhsm(tmp_path, monkeypatch):
    pkcs11 = pytest.importorskip("pkcs11")
    module = service("GL_LIVE_PKCS11")
    conf = tmp_path / "softhsm2.conf"
    (tmp_path / "tokens").mkdir()
    conf.write_text(f"directories.tokendir = {tmp_path / 'tokens'}\nobjectstore.backend = file\n")
    monkeypatch.setenv("SOFTHSM2_CONF", str(conf))
    subprocess.run(
        ["softhsm2-util", "--init-token", "--free", "--label", "gl", "--pin", "1234", "--so-pin", "5678"],
        check=True,
        capture_output=True,
    )
    token = pkcs11.lib(module).get_token(token_label="gl")
    with token.open(rw=True, user_pin="1234") as session:
        params = session.create_domain_parameters(
            pkcs11.KeyType.EC,
            {pkcs11.Attribute.EC_PARAMS: pkcs11.util.ec.encode_named_curve_parameters("secp256r1")},
            local=True,
        )
        public, private = params.generate_keypair(store=False)
        signer = gl.signers.pkcs11(private, public)
        records = a_chain_of_three(gl.sinks.jsonl(tmp_path), signer)
    assert all(r.raw["signature_algorithm"] == "ecdsa-p256-sha256" for r in records)
