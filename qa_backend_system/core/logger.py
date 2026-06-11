import os
import sys

from loguru import logger

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def _safe_add_file_sink(path: str, **kwargs) -> None:
    """
    Prefer async logging, but fall back to sync mode when OS policy blocks
    multiprocessing pipe creation (WinError 5).
    """
    try:
        logger.add(path, enqueue=True, **kwargs)
    except PermissionError:
        logger.add(path, enqueue=False, **kwargs)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 5:
            logger.add(path, enqueue=False, **kwargs)
        else:
            raise


def setup_logger() -> None:
    logger.remove()

    logger.add(
        sys.stdout,
        level="DEBUG",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
    )

    _safe_add_file_sink(
        os.path.join(LOG_DIR, "app_info.log"),
        level="INFO",
        rotation="500 MB",
        retention="30 days",
        encoding="utf-8",
    )

    _safe_add_file_sink(
        os.path.join(LOG_DIR, "app_error.log"),
        level="ERROR",
        rotation="100 MB",
        retention="60 days",
        encoding="utf-8",
        backtrace=True,
        diagnose=False,
    )