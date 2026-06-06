"""
Централизованное логирование для Shroom-бота.

Формат консоли:  12:34:56 | INFO  | handlers.browse | like: user=123
Формат файла:    2026-06-06 12:34:56 | INFO  | handlers.browse | like: user=123

Уровни:
  USER  — действия пользователей
  INFO  — системные события
  DEBUG — SQL и внутренняя логика
  ERROR — исключения
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

USER_LEVEL = 25
logging.addLevelName(USER_LEVEL, "USER")


def _user(self, msg, *args, **kwargs):
    if self.isEnabledFor(USER_LEVEL):
        self._log(USER_LEVEL, msg, args, **kwargs)


logging.Logger.user = _user  # type: ignore


class _ConsoleFormatter(logging.Formatter):
    GREY    = "\033[38;5;245m"
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    MAGENTA = "\033[35m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"

    LEVEL_COLORS = {
        "DEBUG":    "\033[38;5;245m",
        "USER":     "\033[36m",
        "INFO":     "\033[32m",
        "WARNING":  "\033[33m",
        "ERROR":    "\033[31m",
        "CRITICAL": "\033[35m\033[1m",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelname, self.RESET)
        time  = self.formatTime(record, "%H:%M:%S")
        level = f"{color}{record.levelname:<7}{self.RESET}"
        parts = record.name.split(".")
        short = ".".join(parts[-2:]) if len(parts) > 1 else record.name
        name  = f"{self.GREY}{short:<22}{self.RESET}"
        return f"{time} | {level} | {name} | {record.getMessage()}"


class _FileFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        time = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        base = f"{time} | {record.levelname:<7} | {record.name:<30} | {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup(log_dir: str = "logs", debug: bool = False) -> None:
    Path(log_dir).mkdir(exist_ok=True)
    log_file = os.path.join(log_dir, "bot.log")
    level    = logging.DEBUG if debug else logging.INFO

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)

    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FileFormatter())
    root.addHandler(fh)

    for noisy in ("aiohttp", "aiogram.event", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sa_level = logging.DEBUG if debug else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sa_level)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
