import logging
from logging.handlers import TimedRotatingFileHandler
from colorama import Fore, Style, init
import asyncio
from functools import wraps
import time
import copy
import os

# Initialize colorama for colored console output
init(autoreset=True)

class SafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Extends TimedRotatingFileHandler to ignore PermissionError during rollover
    when the log file is temporarily locked.
    """
    def doRollover(self):
        try:
            super().doRollover()
        except PermissionError:
            # File is locked by another process; skip this rollover
            pass

class ColoredFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.YELLOW,
        'WARNING': Fore.MAGENTA,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
        'SUCCESS': Fore.GREEN
    }

    def format(self, record):
        record_copy = copy.copy(record)
        color = self.COLORS.get(record_copy.levelname, '')
        if color:
            record_copy.msg = f"{color}{record_copy.getMessage()}{Style.RESET_ALL}"
        return super().format(record_copy)

class Logger:
    def __init__(self, name=__name__, level=logging.INFO, log_file='app.log'):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # Ensure log directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Define SUCCESS level if not present
        if not hasattr(logging, 'SUCCESS'):
            logging.SUCCESS = 25
            logging.addLevelName(logging.SUCCESS, 'SUCCESS')

        # Prevent adding duplicate handlers
        if not self.logger.handlers:
            # Console handler
            ch = logging.StreamHandler()
            ch.setFormatter(ColoredFormatter('%(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(ch)

            # File handler with delayed open and safe rollover
            fh = SafeTimedRotatingFileHandler(
                log_file,
                when='midnight',
                interval=1,
                backupCount=7,
                encoding='utf-8',
                delay=True
            )
            fh.suffix = "%Y-%m-%d"
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            formatter.converter = time.localtime
            fh.setFormatter(formatter)
            self.logger.addHandler(fh)

    def __get_time(self, func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                self.success(f"Async function {func.__name__} executed in {elapsed:.4f} seconds")
                return result
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.perf_counter()
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                self.success(f"Sync function {func.__name__} executed in {elapsed:.4f} seconds")
                return result
            return sync_wrapper

    @property
    def timeit(self):
        return self.__get_time

    def log(self, level, msg, *args, **kwargs):
        if self.logger.isEnabledFor(level):
            self.logger.log(level, msg, *args, **kwargs)

    def success(self, msg, *args, **kwargs):
        if self.logger.isEnabledFor(logging.SUCCESS):
            self.logger._log(logging.SUCCESS, msg, args, **kwargs)

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)

    def user_message(self, user: str, msg: str, *args, **kwargs):
        formatted = f"[{user}] {msg}"
        self.info(formatted, *args, **kwargs)

    def ai_message(self, model: str, msg: str, *args, **kwargs):
        formatted = f"[AI:{model}] {msg}"
        self.info(formatted, *args, **kwargs)

    def system(self, msg: str, *args, **kwargs):
        formatted = f"[system] {msg}"
        self.info(formatted, *args, **kwargs)


def get_logger(name=__name__, log_file='logging_folder/logs/app.log', level=logging.DEBUG) -> Logger:
    """
    Returns a configured Logger instance with safe file rotation.
    """
    return Logger(name=name, level=level, log_file=log_file)
