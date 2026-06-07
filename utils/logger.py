import os
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

def set_log(project_name: str, export_file: bool = True, print_terminal: bool = True):
    logger = logging.getLogger(project_name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        log_format = '%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s (%(filename)s:%(lineno)d)'
        formatter = logging.Formatter(log_format, datefmt='%Y-%m-%d %H:%M:%S')

        if print_terminal:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        if export_file:
            log_dir = os.path.join(os.getcwd(), "logs", project_name)
            os.makedirs(log_dir, exist_ok=True)
            
            today_str = datetime.now().strftime("%Y%m%d")
            log_file_name = f"{today_str}.log"
            
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, log_file_name),
                maxBytes=10*1024*1024,
                backupCount=5,
                encoding="utf-8"
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    return logger