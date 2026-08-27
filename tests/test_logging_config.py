import logging
import tempfile
import unittest
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.logging_config import LOG_FILE, configure_logging, logger


class LoggingConfigTest(unittest.TestCase):
    def test_logger_has_console_and_rotating_file_handlers(self):
        handler_types = {type(handler).__name__ for handler in logger.handlers}
        rotating_handler = next(
            handler
            for handler in logger.handlers
            if isinstance(handler, RotatingFileHandler)
        )

        self.assertIn("StreamHandler", handler_types)
        self.assertEqual(rotating_handler.maxBytes, 5 * 1024 * 1024)
        self.assertEqual(rotating_handler.backupCount, 5)

    def test_logger_writes_to_expected_file(self):
        logger.info("logging_config_test")
        for handler in logger.handlers:
            handler.flush()

        self.assertTrue(LOG_FILE.exists())

    def test_uvicorn_request_logs_are_suppressed(self):
        self.assertTrue(logging.getLogger("uvicorn.access").disabled)
        self.assertGreaterEqual(
            logging.getLogger("uvicorn.error").level,
            logging.WARNING,
        )

    def test_unwritable_log_path_falls_back_to_console(self):
        with tempfile.TemporaryDirectory() as directory:
            blocked_parent = Path(directory) / "not-a-directory"
            blocked_parent.write_text("blocked", encoding="utf-8")

            fallback = configure_logging(
                logger_name="agent.test.fallback",
                log_file=blocked_parent / "agent.log",
            )

        self.assertTrue(
            any(type(handler) is logging.StreamHandler for handler in fallback.handlers)
        )
        self.assertFalse(
            any(isinstance(handler, RotatingFileHandler) for handler in fallback.handlers)
        )


if __name__ == "__main__":
    unittest.main()
