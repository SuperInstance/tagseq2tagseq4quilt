"""Test-support utilities for the pytest suite.

The root ``tests/conftest.py`` parametrizes fixtures over available devices
and standard dtypes; this module backs those fixtures. It was missing from
the tree, which blocked pytest collection for the entire suite.
"""
import torch


def get_available_devices():
    """Devices tests can actually run on here: always cpu, cuda if present."""
    return ["cpu", "cuda"] if torch.cuda.is_available() else ["cpu"]


def get_test_dtypes():
    """Standard dtypes for numerical fixtures."""
    return [torch.float32]
