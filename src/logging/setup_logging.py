# src/utils/logger.py
import logging
import sys

def setup_logging():
    """Setup logging with handler clearing to prevent duplication"""
    
    # Get or create root logger
    logger = logging.getLogger("fastapi_app")
    
    # ✅ CRITICAL: Clear existing handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    
    logger.setLevel(logging.INFO)
    
    # Remove all handlers from root logger too
    root_logger = logging.getLogger()
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    # Create fresh handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    
    logger.addHandler(console_handler)
    root_logger.addHandler(console_handler)
    
    return logger