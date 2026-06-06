"""
Логирование Shroom-бота.

Консоль:  18:42:01.213 ●  like: user=123 → 456          [browse]
Файл:     2026-06-06 18:42:01.213 | USER    | browse | like: user=123 → 456

Уровни:
  USER  25  — действия пользователей (лайк, мэтч, регистрация)
  INFO  20  — старт, БД, webhook
  DEBUG 10  — SQL, внутренности (только файл)
  ERROR 40  — исключения (консоль + файл с traceback)
"""
import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ── Кастомный уровень USER ───────────────────────────────────────
USER_LEVEL = 25
logging.addLevelName(USER_LEVEL, "USER")


def _user(self, msg, *args, **kwargs):
    if self.isEnabledFor(USER_LEVEL):
        self._log(USER_LEVEL, msg, args, **kwargs)


logging.Logger.user = _user  # type: ignore


# ── Короткое имя модуля ──────────────────────────────────────────
def _short_name(name: str) -> str:
    """
    bot.handlers.browse  →  browse
    bot.middlewares.session  →  session
    sqlalchemy.engine  →  sqlalchemy
    """
    parts = name.split(".")
    return parts[-1] if parts[-1] not in ("py",) else parts[-2]


# ── Консольный форматтер ─────────────────────────────────────────
class _ConsoleFormatter(logging.Formatter):
    """
    Формат одной строки:
        18:42:01.213 ●  like: user=123 → 456          [browse]

    Иконка + цвет сразу показывают уровень без чтения слова.
    Модуль — в конце, приглушённый, не мешает читать сообщение.
    """

    R = "\033[0m"          # reset
    DIM = "\033[2m"        # тусклый (время, модуль)
    BOLD = "\033[1m"

    # (иконка, цвет текста сообщения)
    STYLES: dict[str, tuple[str, str]] = {
        "DEBUG":    ("·",  "\033[38;5;240m"),   # тёмно-серый
        "USER":     ("●",  "\033[38;5;117m"),   # голубой
        "INFO":     ("◆",  "\033[38;5;83m"),    # зелёный
        "WARNING":  ("▲",  "\033[38;5;214m"),   # оранжевый
        "ERROR":    ("✕",  "\033[38;5;203m"),   # красный
        "CRITICAL": ("!!!", "\033[1;38;5;196m"), # жирный красный
    }

    def format(self, record: logging.LogRecord) -> str:
        icon, color = self.STYLES.get(record.levelname, ("?", self.R))
        time   = self.formatTime(record, "%H:%M:%S") + f".{record.msecs:03.0f}"
        module = _short_name(record.name)
        msg    = record.getMessage()

        # выравниваем модуль по правому краю (ширина 48 символов на msg)
        line = f"{self.DIM}{time}{self.R}  {color}{icon}  {msg}{self.R}"

        # модуль в конце, приглушённый
        pad = max(1, 52 - len(msg))
        line += f"{' ' * pad}{self.DIM}[{module}]{self.R}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)

        return line


# ── Файловый форматтер ───────────────────────────────────────────
class _FileFormatter(logging.Formatter):
    """
    Без ANSI. Легко читается через tail -f и grep.
    grep USER bot.log     — только действия юзеров
    grep ERROR bot.log    — только ошибки
    grep 'user=123' bot.log — всё про конкретного юзера
    """

    def format(self, record: logging.LogRecord) -> str:
        msec   = f"{record.msecs:03.0f}"
        time   = self.formatTime(record, "%Y-%m-%d %H:%M:%S") + f".{msec}"
        level  = f"{record.levelname:<8}"
        module = f"{_short_name(record.name):<16}"
        base   = f"{time} | {level} | {module} | {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ── Инициализация ────────────────────────────────────────────────
def setup(log_dir: str = "logs", debug: bool = False) -> None:
    Path(log_dir).mkdir(exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Консоль: USER + INFO + WARNING + ERROR (не DEBUG)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(USER_LEVEL)
    console.setFormatter(_ConsoleFormatter())
    root.addHandler(console)

    # Файл: всё включая DEBUG, ротация 10 МБ × 5
    fh = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FileFormatter())
    root.addHandler(fh)

    # Заглушки шумных библиотек
    for noisy in ("aiohttp", "aiogram.event", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    sa_level = logging.DEBUG if debug else logging.WARNING
    logging.getLogger("sqlalchemy.engine").setLevel(sa_level)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    return logging.getLogger(name)
