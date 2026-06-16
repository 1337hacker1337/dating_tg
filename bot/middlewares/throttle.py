"""
bot/middlewares/throttle.py — антиспам.

Вешается ОДНИМ общим экземпляром на dp.message.outer_middleware и
dp.callback_query.outer_middleware (см. main.py). Это самый надёжный способ:
outer-middleware гарантированно вызывается для КАЖДОГО сообщения и КАЖДОГО
нажатия инлайн-кнопки до фильтров и хэндлеров. Один экземпляр на оба
обсервера → кулдауны общие по user_id.

Ограничивает три вида действий (независимые кулдауны):
  • callback_query — инлайн-кнопки (лайк/диз/навигация) — CALLBACK_RATE;
  • кнопки нижнего меню (reply-keyboard, MENU_BUTTON_TEXTS) — MENU_RATE;
  • команды (/...) — COMMAND_RATE.

Произвольный текст НЕ троттлится (регистрация, редактирование, рассылка).

Middleware устойчив к типу события: принимает Message, CallbackQuery или
Update (на случай регистрации на dp.update) и сам достаёт нужное.
"""
import time
from typing import Any, Awaitable, Callable, Optional, Tuple

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot import logger as log
from bot.constants import MENU_BUTTON_TEXTS

_log = log.get(__name__)

COMMAND_RATE  = 2.0     # сек между командами
CALLBACK_RATE = 0.6     # сек между нажатиями инлайн-кнопок
MENU_RATE     = 1.0     # сек между нажатиями кнопок нижнего меню
CLEANUP_EVERY = 1000


def _extract(event) -> Tuple[Optional[Any], Optional[Any]]:
    """Достаёт (message, callback_query) из Message | CallbackQuery | Update."""
    name = type(event).__name__
    if name == "Message":
        return event, None
    if name == "CallbackQuery":
        return None, event
    if name == "Update":
        return getattr(event, "message", None), getattr(event, "callback_query", None)
    # неизвестный тип — пробуем по атрибутам
    if getattr(event, "data", None) is not None and not hasattr(event, "text"):
        return None, event
    if hasattr(event, "text") and getattr(event, "data", None) is None:
        return event, None
    return getattr(event, "message", None), getattr(event, "callback_query", None)


class CommandThrottleMiddleware(BaseMiddleware):
    def __init__(
        self,
        command_rate:  float = COMMAND_RATE,
        callback_rate: float = CALLBACK_RATE,
        menu_rate:     float = MENU_RATE,
    ) -> None:
        self._cmd_rate:  float = command_rate
        self._cb_rate:   float = callback_rate
        self._menu_rate: float = menu_rate
        self._last:   dict[tuple[int, str], float] = {}
        self._checks: int = 0

    def _maybe_cleanup(self, now: float) -> None:
        self._checks += 1
        if self._checks % CLEANUP_EVERY:
            return
        cutoff     = now - 60.0
        self._last = {k: ts for k, ts in self._last.items() if ts > cutoff}

    def _hit(self, user_id: int, kind: str, rate: float, now: float) -> float:
        """0.0 — пропускаем (и фиксируем время); >0 — сколько ещё ждать (сек)."""
        key     = (user_id, kind)
        elapsed = now - self._last.get(key, 0.0)
        if elapsed < rate:
            return round(rate - elapsed, 1)
        self._last[key] = now
        return 0.0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event:   TelegramObject,
        data:    dict[str, Any],
    ) -> Any:
        msg, cb = _extract(event)
        now = time.monotonic()

        # ── Инлайн-кнопки ─────────────────────────────────────────
        if cb is not None and getattr(cb, "from_user", None) is not None:
            self._maybe_cleanup(now)
            if self._hit(cb.from_user.id, "cb", self._cb_rate, now):
                try:
                    await cb.answer()  # снять «часики», тихо проглотить
                except Exception:
                    pass
                return
            return await handler(event, data)

        # ── Сообщения: команды и кнопки меню ──────────────────────
        if msg is not None and getattr(msg, "text", None) and getattr(msg, "from_user", None):
            text = msg.text

            if text.startswith("/"):
                self._maybe_cleanup(now)
                wait = self._hit(msg.from_user.id, "cmd", self._cmd_rate, now)
                if wait:
                    _log.info("throttle cmd: user=%s cmd=%s wait=%.1fs",
                              msg.from_user.id, text.split()[0], wait)
                    try:
                        await msg.answer(f"⏳  {wait}с.")
                    except Exception:
                        pass
                    return
                return await handler(event, data)

            if text in MENU_BUTTON_TEXTS:
                self._maybe_cleanup(now)
                if self._hit(msg.from_user.id, "menu", self._menu_rate, now):
                    return  # тихо глотаем «дребезг»
                return await handler(event, data)

        return await handler(event, data)
