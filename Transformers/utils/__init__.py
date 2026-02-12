import logging
import argparse

def init_logging_config():
    level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s (%(filename)s:%(lineno)d) - %(message)s",
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    _logger = logging.getLogger("Transformers")
    _logger.setLevel(level)

    # Disable some noisy logs if needed
    # logging.getLogger("httpx").setLevel(logging.WARNING)

    return _logger

logger = init_logging_config()
