from loguru import logger

from kili_examples.config import settings
from kili_examples.logging import setup_logging
from kili_examples.paths import PROJECT_ROOT, RAW_DIR


def main() -> None:
    """Main entrypoint to run the application"""
    # Setup logging
    setup_logging()

    # Start the application
    logger.info("Application started (env: {})", settings.environment)
    logger.info("Project root: {}", PROJECT_ROOT)
    logger.info("Raw data directory: {}", RAW_DIR)


if __name__ == "__main__":
    main()
