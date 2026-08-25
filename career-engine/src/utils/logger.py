"""Rich-based logger configuration for Career Engine."""

import logging
from rich.console import Console
from rich.logging import RichHandler

console = Console()


def setup_logger(name: str = "career_engine", level: str = "INFO") -> logging.Logger:
    """Configure and return a structured Rich logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers
    if not logger.handlers:
        handler = RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            markup=True
        )
        handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
        logger.addHandler(handler)

    return logger


logger = setup_logger()
