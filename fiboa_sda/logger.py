import logging
import time

from fiboa_sda.settings import get_settings


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    level = logging.DEBUG if get_settings().DEBUG else logging.INFO
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(level)
    return logger


logger = get_logger(__name__)


class TimerFunc:
    """Decorator is not pickleable, use a class instead."""
    def __init__(self, func):
        self.func = func

    def __call__(self, *args, **kwargs):
        start = time.perf_counter()
        result = self.func(*args, **kwargs)
        end = time.perf_counter()
        logger.info(f"Function {self.func.__name__!r} executed in {(end-start):.4f}s")
        return result
