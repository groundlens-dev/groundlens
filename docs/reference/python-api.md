# Python API

Everything importable from the top-level `groundlens` package. The reference
below is generated from the docstrings in the source, so it always matches the
installed version.

```{contents}
:local:
:depth: 1
```

## Verifying

```{eval-rst}
.. autoclass:: groundlens.Verifier
   :members: check, seal, store, judge_prompt

.. autofunction:: groundlens.verify
.. autofunction:: groundlens.verify_run
```

## Records

```{eval-rst}
.. autoclass:: groundlens.Record
   :members:
   :show-inheritance:

.. autoclass:: groundlens.RunRecord
   :members:
   :show-inheritance:
```

## Evidence

```{eval-rst}
.. autoclass:: groundlens.Evidence
   :members:
```

## Judges

```{eval-rst}
.. automodule:: groundlens.judges
   :members: openai_compatible, azure_openai, bedrock, Judge
```

## Measurement and replay

```{eval-rst}
.. automodule:: groundlens.measure
   :members: sample, read_labels, measure, replay, sign, verify_signed
```

## Signers

```{eval-rst}
.. automodule:: groundlens.signers
   :members: local_key, aws_kms, azure_key_vault, pkcs11, Signer
```

## Sinks

```{eval-rst}
.. automodule:: groundlens.sinks
   :members: jsonl, s3_object_lock, azure_blob, postgres, Sink, StoreError, ChainConflict
```

## Policies

```{eval-rst}
.. autoclass:: groundlens.Policy
   :members:
```

## Constants

```{py:data} groundlens.ENGINE_VERSION
The version string of the compiled GLV engine, read from the extension at
import time. Recorded in every evidence record as ``engine_version``.
```

```{py:data} groundlens.__version__
The version of the ``groundlens`` Python package.
```
