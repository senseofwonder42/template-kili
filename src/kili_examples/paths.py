"""Project paths, resolved from the package location and not from the CWD."""

from pathlib import Path
from typing import Final

# src/<package>/paths.py -> src/<package> -> src -> project root
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

DATA_DIR: Final[Path] = PROJECT_ROOT / "data"
RAW_DIR: Final[Path] = DATA_DIR / "raw"
INTERIM_DIR: Final[Path] = DATA_DIR / "interim"
PROCESSED_DIR: Final[Path] = DATA_DIR / "processed"
EXTERNAL_DIR: Final[Path] = DATA_DIR / "external"

MODELS_DIR: Final[Path] = PROJECT_ROOT / "models"
REPORTS_DIR: Final[Path] = PROJECT_ROOT / "reports"
FIGURES_DIR: Final[Path] = REPORTS_DIR / "figures"
