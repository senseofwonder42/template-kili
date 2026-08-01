import os
import random

import pytest

from kili_examples.seed import set_seed


def test_set_seed_makes_the_standard_library_deterministic():
    """Re-seeding replays the same sequence."""
    set_seed(42)
    first = [random.random() for _ in range(5)]

    set_seed(42)

    assert [random.random() for _ in range(5)] == first


def test_set_seed_exports_pythonhashseed():
    """Hash randomization is pinned too."""
    set_seed(7)

    assert os.environ["PYTHONHASHSEED"] == "7"


def test_set_seed_makes_numpy_deterministic():
    """NumPy is seeded as well when it is installed."""
    np = pytest.importorskip("numpy")

    set_seed(42)
    first = np.random.rand(5).tolist()

    set_seed(42)

    assert np.random.rand(5).tolist() == first
