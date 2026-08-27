import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import log_dir


LOGGER_NAME = "agent.server"
LOG_FILE = log_dir() / "agent.log"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(logger_name=LOGGER_NAME, log_file=LOG_FILE):
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)

    logger = logging.getLogger(logger_name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    try:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("file_logging_unavailable error_type=%s", type(exc).__name__)
    else:
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    return logger


logger = configure_logging()
