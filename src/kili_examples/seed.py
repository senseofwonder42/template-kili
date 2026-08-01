"""Reproducibility helpers."""

import os
import random
from contextlib import suppress


def set_seed(seed: int) -> None:
    """Seed every random number generator available in the environment.

    Seeds the standard library, hash randomization, and — when the libraries
    are installed — NumPy, PyTorch and TensorFlow.

    Args:
        seed: The seed to apply.
    """
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)

    with suppress(ImportError):
        import numpy as np

        np.random.seed(seed)

    with suppress(ImportError):
        import torch

        torch.manual_seed(seed)

    with suppress(ImportError):
        import tensorflow as tf

        tf.random.set_seed(seed)
