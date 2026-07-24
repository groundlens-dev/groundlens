"""Fuzz the deterministic numeric-to-plain-language output layer.

check_for_verification turns a consistency score into a Check. It must be
total: any float (including nan and inf) must yield a renderable reading and
never raise. This target exercises that contract.
"""

import sys

import atheris

with atheris.instrument_imports():
    from groundlens.check import check_for_verification


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    consistency = fdp.ConsumeFloat()
    n_samples = fdp.ConsumeIntInRange(0, 10000)
    reading = check_for_verification(consistency, n_samples=n_samples)
    # These must never crash on any input.
    reading.render()
    _ = (reading.level, reading.label, reading.escalate)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
