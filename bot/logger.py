"""
Централизованное логирование для Shroom-бота.

Формат консоли:  12:34:56 | INFO  | handlers.browse | like: user=123 → 456
Формат файла:    2026-06-06 12:34:56 | INFO  | handlers.browse | like: user=123 → 456

Уровни:
  USER  — действия пользователей (регистрация, лайк, мэтч и т.д.)
  INFO  — системные события (старт, подключение к БД)
  DEBUG — SQL и внутренняя логика
  ERROR — исключения
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path


# ── Кастомный уровень USER (между INFO и DEBUG) ──────────────────
USER_LEVEL = 25
logging.addLevelName(USER_LEVEL, "USER")


def _user(self, msg, *args, **kwargs):
    if self.isEnabledFor(USER_LEVEL):
        self._log(USER_LEVEL, msg, args, **kwargs)


logging.Logger.user = _user  # type: ignore


# ── Форматтеры ───────────────────────────────────────────────────

class _ConsoleFormatter(logging.Formatter):
    """Цветной короткий формат для консоли."""

    GREY    = "\033[38;5;245m"
    CYAN    = "\033[36m"
    GREEN   = "\033[32m"
    YELLOW  = "\033[33m"
    RED     = "\033[31m"
    MAGENTA = "\033[35m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"

    LEVEL_COLORS = {
        "DEBUG":   GREY,
        "USER":    CYAN,
        "INFO":    GREEN,
        "WARNING": YELLOW,
        "ERROR":   RED,
        "CRITICAL": MAGENTA + BOLD,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelname, self.RESET)
        time  = self.formatTime(record, "%H:%M:%S")
        level = f"{color}{record.levelname:<7}{self.RESET}"
        # Короткое имя модуля (последние 2 части)
        name_parts = record.name.split(".")
        short_name = ".".join(name_parts[-2:]) if len(name_parts) > 1 else record.name
        name  = f"{self.GREY}{short_name:<22}{self.RESET}"
        msg   = record.getMessage()
        return f"{time} | {level} | {name} | {msg}"


class _FileFormatter(logging.Formatter):
    """Полный формат для файла без ANSI-кодов."""

    def format(self, record: logging.LogRecord) -> str:
        time  = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        level = f"{record.levelname:<7}"
        name  = f"{record.name:<30}"
        msg   = record.getMessage()
        base  = f"{time} | {level} | {name} | {msg}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ── Инициализация ────────────────────────────────────────────────

def setup(log_dir: str = "logs", debug: bool = False) -> None:
    """
    Вызвать один раз при старте бота.
    Настраивает root-логгер + подавляет шум от сторонних библиотек.
    """
    Path(log_dir).mkdir(exist_ok=True)
    log_file = os.path.join(log_dir, "bot.log")

    level = logging.DEBUG if debug else logging.INFO

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # перехватываем всё, фильтруем в handlers

    # ── Консоль ──────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)

    # ── Файл с ротацией (10 МБ × 5 файлов) ──────────────────────
    fh = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)  # в файл пишем всё
    fh.setFormatter(_FileFormatter())
    root.addHandler(fh)

    # ── Заглушки для шумных библиотек ────────────────────────────
    for noisy in ("aiohttp", "aiogram.event", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # SQLAlchemy: engine показываем только в DEBUG-режиме
    sa_level = logging.DEBUG if debug else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sa_level)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    """Короткий хелпер вместо logging.getLogger()."""
    return logging.getLogger(name)
