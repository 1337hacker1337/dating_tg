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


def _short_name(name: str) -> str:
    parts = name.split(".")
    return parts[-1] if parts[-1] not in ("py",) else parts[-2]


class _ConsoleFormatter(logging.Formatter):
    R = "\033[0m"; DIM = "\033[2m"; BOLD = "\033[1m"
    STYLES = {
        "DEBUG":    ("·",  "\033[38;5;240m"),
        "USER":     ("●",  "\033[38;5;117m"),
        "INFO":     ("◆",  "\033[38;5;83m"),
        "WARNING":  ("▲",  "\033[38;5;214m"),
        "ERROR":    ("✕",  "\033[38;5;203m"),
        "CRITICAL": ("!!!", "\033[1;38;5;196m"),
    }

    def format(self, record):
        icon, color = self.STYLES.get(record.levelname, ("?", self.R))
        time = self.formatTime(record, "%H:%M:%S") + f".{record.msecs:03.0f}"
        module = _short_name(record.name)
        msg = record.getMessage()
        line = f"{self.DIM}{time}{self.R}  {color}{icon}  {msg}{self.R}"
        pad = max(1, 52 - len(msg))
        line += f"{' ' * pad}{self.DIM}[{module}]{self.R}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class _FileFormatter(logging.Formatter):
    def format(self, record):
        msec = f"{record.msecs:03.0f}"
        time = self.formatTime(record, "%Y-%m-%d %H:%M:%S") + f".{msec}"
        level = f"{record.levelname:<8}"
        module = f"{_short_name(record.name):<16}"
        base = f"{time} | {level} | {module} | {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def setup(log_dir="logs", debug=False):
    Path(log_dir).mkdir(exist_ok=True)
    if sys.platform == "win32":
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8",
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
