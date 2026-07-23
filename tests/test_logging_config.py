import logging
import unittest
from logging.handlers import RotatingFileHandler

from app.logging_config import LOG_FILE, logger


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


if __name__ == "__main__":
    unittest.main()
