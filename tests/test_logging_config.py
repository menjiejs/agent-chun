import unittest
from logging.handlers import RotatingFileHandler

from app.logging_config import LOG_FILE, logger


class LoggingConfigTest(unittest.TestCase):
    def test_logger_has_console_and_rotating_file_handlers(self):
        handler_types = {type(handler).__name__ for handler in logger.handlers}

        self.assertIn("StreamHandler", handler_types)
        self.assertTrue(
            any(isinstance(handler, RotatingFileHandler) for handler in logger.handlers)
        )

    def test_logger_writes_to_expected_file(self):
        logger.info("logging_config_test")
        for handler in logger.handlers:
            handler.flush()

        self.assertTrue(LOG_FILE.exists())


if __name__ == "__main__":
    unittest.main()
