"""The encoder adapter, tested without a model.

`SentenceTransformerEncoder` itself needs a checkpoint, so it is verified by
`scripts/verify_encoder.py` on a machine that has one. But the part that broke
on Apple Silicon -- getting the model's output onto the host before numpy
touches it -- is a pure function and can be tested here, so it is.
"""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy", reason="numpy arrives with the [encoder] extra")

from groundlens._encode import _to_host_array  # noqa: E402


class AcceleratorTensor:
    """Stands in for a torch tensor living on MPS or CUDA.

    The behaviour that matters: numpy cannot read it where it is. Real MPS
    tensors raise ``TypeError: can't convert mps:0 device type tensor to numpy``
    from ``__array__``, so this raises from the same place. It becomes readable
    only after ``.detach().cpu().numpy()``.
    """

    def __init__(self, rows: list[list[float]], device: str = "mps:0") -> None:
        self._rows = rows
        self.device = device
        self.detached = False
        self.moved = False

    def __array__(self, *_: object, **__: object) -> object:
        msg = f"can't convert {self.device} device type tensor to numpy"
        raise TypeError(msg)

    def __len__(self) -> int:
        return len(self._rows)

    def detach(self) -> AcceleratorTensor:
        self.detached = True
        return self

    def cpu(self) -> AcceleratorTensor:
        self.moved = True
        return self

    def numpy(self) -> object:
        if not self.moved:
            msg = f"can't convert {self.device} device type tensor to numpy"
            raise TypeError(msg)
        return np.asarray(self._rows, dtype=np.float32)


ROWS = [[1.0, 0.0, 0.0], [0.0, 2.0, 0.0]]


def test_an_accelerator_tensor_is_brought_to_the_host() -> None:
    """The Apple Silicon crash, as a regression test.

    A live MPS tensor reached np.asarray and raised. It has to be detached and
    moved first -- and this cannot be caught by the fake encoder, which returns
    plain lists, which is precisely why verify_encoder.py exists.
    """
    tensor = AcceleratorTensor(ROWS)
    out = _to_host_array(tensor)
    assert tensor.detached and tensor.moved
    assert out.tolist() == ROWS
    assert out.dtype == np.float32


def test_a_cuda_tensor_takes_the_same_path() -> None:
    tensor = AcceleratorTensor(ROWS, device="cuda:0")
    assert _to_host_array(tensor).tolist() == ROWS


def test_a_plain_numpy_array_passes_through_unharmed() -> None:
    assert _to_host_array(np.asarray(ROWS, dtype=np.float32)).tolist() == ROWS


def test_plain_lists_work_too() -> None:
    assert _to_host_array(ROWS).tolist() == ROWS


def test_an_empty_result_does_not_explode() -> None:
    assert _to_host_array([]).shape == (0,)


def test_output_is_always_float32() -> None:
    """Rounding to a single dtype keeps the profile hash stable across backends."""
    assert _to_host_array(np.asarray(ROWS, dtype=np.float64)).dtype == np.float32
