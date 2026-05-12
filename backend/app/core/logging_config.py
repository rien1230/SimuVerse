"""Logging setup so backend requests and sim output stay easy to follow.

This is the one place that defines the backend log format and default noise
filtering for third-party libraries.
"""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    """Set up a single stdout handler with a consistent format for the whole app.


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
