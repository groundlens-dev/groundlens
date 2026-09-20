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
.. autofunction:: groundlens.verify
.. autofunction:: groundlens.verify_run
.. autofunction:: groundlens.proofread
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

.. autoclass:: groundlens.Proofread
   :members:

.. autoclass:: groundlens.Anchor
   :members:

.. autoclass:: groundlens.AnchorKind
   :members:

.. autoclass:: groundlens.Span
   :members:

.. autofunction:: groundlens.as_evidence
```

## Policies

```{eval-rst}
.. autoclass:: groundlens.Policy
   :members:
```

## Bundles and encoders

```{eval-rst}
.. autoclass:: groundlens.Bundle
   :members:

.. autoclass:: groundlens.Encoder
   :members:

.. autoclass:: groundlens.WindowEncoding
   :members:
```

## Calibration

```{eval-rst}
.. autofunction:: groundlens.calibrate
.. autoclass:: groundlens.OperatingPoint
   :members:
.. autofunction:: groundlens.adaptive_k
```

## Constants

```{eval-rst}
.. autodata:: groundlens.NOTE_CODES
```

```{py:data} groundlens.ENGINE_VERSION
The version string of the compiled GLV engine, read from the extension at
import time. Recorded in every evidence record as ``engine_version``.
```

```{py:data} groundlens.__version__
The version of the ``groundlens`` Python package.
```
