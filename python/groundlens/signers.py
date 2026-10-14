# SPDX-FileCopyrightText: 2026 Javier Marín <javier@jmarin.info>
#
# SPDX-License-Identifier: Apache-2.0

"""Who signs a record.

Every record is signed. Who holds the key is your choice:

- :func:`local_key`: an Ed25519 key the process holds. For development, tests
  and single-machine use; whoever can read the seed can sign as you.
- :func:`aws_kms`, :func:`azure_key_vault`, :func:`pkcs11`: a key that never
  leaves a key service or an HSM. GroundLens builds the record, asks the
  service to sign its ``record_hash``, checks the signature, and only then
  returns the record. These services sign with ECDSA on P-256, so the record
  says ``signature_algorithm: ecdsa-p256-sha256``.

You pass the client you already use (``boto3``, ``azure-keyvault-keys``,
``python-pkcs11``). GroundLens does not depend on any of them and opens no
connection of its own.
"""

from __future__ import annotations

import hashlib
from typing import Any, Protocol, runtime_checkable

from groundlens import _engine

ED25519 = "ed25519"
ECDSA_P256_SHA256 = "ecdsa-p256-sha256"


@runtime_checkable
class Signer(Protocol):
    """Anything that can sign the bytes of a ``record_hash``.

    ``sign`` returns the signature: for ``ecdsa-p256-sha256``, ``r || s`` or
    DER; ``public_key`` returns SEC1 or DER SubjectPublicKeyInfo bytes. The
    engine checks the signature against the key before it accepts a record.
    """

    algorithm: str

    def public_key(self) -> bytes: ...

    def sign(self, message: bytes) -> bytes: ...


class LocalKey:
    """An Ed25519 key held by this process. The engine signs with it directly."""

    algorithm = ED25519

    def __init__(self, seed_hex: str) -> None:
        if len(seed_hex) != 64:
            raise ValueError("a local key is a 32-byte Ed25519 seed, 64 hex characters")
        self.seed_hex = seed_hex

    def public_key(self) -> bytes:  # pragma: no cover - the engine signs local keys itself
        raise NotImplementedError("a local key is used by the engine directly")

    def sign(self, message: bytes) -> bytes:  # pragma: no cover
        raise NotImplementedError("a local key is used by the engine directly")


def local_key(seed_hex: str | None = None) -> LocalKey:
    """An Ed25519 key in this process, for development. ``None`` makes a new one.

    Keep the seed in a secret manager; ``groundlens keygen`` prints a fresh one.
    """
    return LocalKey(seed_hex or _engine.keygen())


class AwsKms:
    """A P-256 key in AWS KMS (key spec ``ECC_NIST_P256``, usage ``SIGN_VERIFY``)."""

    algorithm = ECDSA_P256_SHA256

    def __init__(self, client: Any, key_id: str) -> None:
        self.client = client
        self.key_id = key_id
        self._public_key: bytes | None = None

    def public_key(self) -> bytes:
        if self._public_key is None:
            answer = self.client.get_public_key(KeyId=self.key_id)
            spec = answer.get("KeySpec") or answer.get("CustomerMasterKeySpec")
            if spec and spec != "ECC_NIST_P256":
                raise ValueError(f"KMS key {self.key_id} is {spec}; GroundLens signs with ECC_NIST_P256 keys")
            self._public_key = bytes(answer["PublicKey"])
        return self._public_key

    def sign(self, message: bytes) -> bytes:
        answer = self.client.sign(
            KeyId=self.key_id,
            Message=message,
            MessageType="RAW",
            SigningAlgorithm="ECDSA_SHA_256",
        )
        return bytes(answer["Signature"])


def aws_kms(client: Any, key_id: str) -> AwsKms:
    """Sign with a KMS key. ``client`` is ``boto3.client("kms")``."""
    return AwsKms(client, key_id)


class AzureKeyVault:
    """A P-256 key in Azure Key Vault or Managed HSM (``EC``, curve ``P-256``).

    Experimental: Key Vault has no emulator, so CI tests this signer only
    against a stand-in with the SDK's call shape. The other signers run
    against real software in CI (``tests/test_live_services.py``).
    """

    algorithm = ECDSA_P256_SHA256

    def __init__(self, crypto_client: Any, key: Any) -> None:
        self.crypto_client = crypto_client
        self.key = key

    def public_key(self) -> bytes:
        jwk = getattr(self.key, "key", self.key)
        crv = getattr(jwk, "crv", None)
        crv = str(getattr(crv, "value", crv) or "P-256")
        if crv.upper() != "P-256":
            raise ValueError(f"Key Vault key curve is {crv}; GroundLens signs with P-256 keys")
        x, y = bytes(jwk.x), bytes(jwk.y)
        return b"\x04" + x.rjust(32, b"\x00") + y.rjust(32, b"\x00")

    def sign(self, message: bytes) -> bytes:
        # Key Vault signs a digest the caller computes; ES256 is ECDSA P-256
        # over SHA-256, the same signature AWS KMS gives over the raw message.
        digest = hashlib.sha256(message).digest()
        return bytes(self.crypto_client.sign("ES256", digest).signature)


def azure_key_vault(crypto_client: Any, key: Any) -> AzureKeyVault:
    """Sign with a Key Vault key.

    ``crypto_client`` is an ``azure.keyvault.keys.crypto.CryptographyClient``
    for the key, and ``key`` the ``KeyVaultKey`` (from ``KeyClient.get_key``),
    whose public part goes into every record.
    """
    return AzureKeyVault(crypto_client, key)


class Pkcs11:
    """A P-256 key in an HSM or token reached through PKCS#11."""

    algorithm = ECDSA_P256_SHA256

    def __init__(self, private_key: Any, public_key: Any) -> None:
        self.private_key = private_key
        self.public_key_object = public_key

    def public_key(self) -> bytes:
        from pkcs11 import Attribute  # noqa: PLC0415 - optional, the caller's library

        point = bytes(self.public_key_object[Attribute.EC_POINT])
        # CKA_EC_POINT is a DER OCTET STRING around the SEC1 point.
        if len(point) == 67 and point[0] == 0x04 and point[1] == 0x41:
            point = point[2:]
        return point

    def sign(self, message: bytes) -> bytes:
        from pkcs11 import Mechanism  # noqa: PLC0415 - optional, the caller's library

        # CKM_ECDSA over a digest computed here. Every PKCS#11 token has it;
        # CKM_ECDSA_SHA256 is optional, and SoftHSM and many HSMs lack it.
        digest = hashlib.sha256(message).digest()
        return bytes(self.private_key.sign(digest, mechanism=Mechanism.ECDSA))


def pkcs11(private_key: Any, public_key: Any) -> Pkcs11:
    """Sign with a key in an HSM. ``private_key`` and ``public_key`` are
    ``python-pkcs11`` key objects from an open session (an ``EC`` key pair on
    P-256)."""
    return Pkcs11(private_key, public_key)
