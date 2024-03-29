import logging
import os
from logging.handlers import RotatingFileHandler


def setup_custom_logger(name):
    LOG_FILE_HANDLER_ACTIVATED = os.environ.get("LOG_FILE_HANDLER_ACTIVATED", True)
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_FILE = os.environ.get("LOG_FILE", "log/portal_client.log")
    LOG_BACKUP_COUNT = int(os.environ.get("LOG_BACKUP_COUNT", 5))
    LOG_MAX_BYTES = int(os.environ.get("LOG_MAX_BATES", 1073741824))

    formatter = logging.Formatter(
        fmt="%(asctime)s - [%(levelname)s] -  [%(pathname)s:%(funcName)s:%(lineno)d]  - %(message)s"
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    # Create the log directory if it does not exist
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    file_handler = RotatingFileHandler(
        maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, filename=LOG_FILE
    )
    file_handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)
    logger.addHandler(handler)
    if LOG_FILE_HANDLER_ACTIVATED:
        logger.addHandler(file_handler)
    return logger
