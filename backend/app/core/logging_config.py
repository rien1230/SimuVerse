"""Logging setup so backend requests and sim output stay easy to follow.

This is the one place that defines the backend log format and default noise
filtering for third-party libraries.
"""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Set up a single stdout handler with a consistent format for the whole app.

    Called once at startup in main.py. The format includes timestamp, level,
    logger name, and message so it's easy to trace which module produced each line.

    Args:
        level: Logging level string (e.g. "INFO", "DEBUG"). Falls back to INFO
               if an unrecognised string is passed.
    """
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Write all logs to stdout (rather than stderr) so they're easier to capture in tests
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # getattr fallback means a typo like "DEBG" won't crash startup
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Only add the handler if nothing is already attached — avoids duplicate
    # log lines when configure_logging() is accidentally called more than once
    if not root.handlers:
        root.addHandler(handler)

    # HuggingFace and PyTorch are very chatty at INFO level, dial them back
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("torch").setLevel(logging.WARNING)
