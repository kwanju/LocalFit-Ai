import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: str = "logs", level: str = "DEBUG") -> None:
    """Configure loguru: colored stderr (INFO+) and rotating file (DEBUG+)."""
    logger.remove()

    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path / "localfit_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        level=level,
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} — {message}",
    )


__all__ = ["logger", "setup_logging"]
