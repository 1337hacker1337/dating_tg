"""
bot/middlewares/command_throttle.py
Антиспам для команд. Регистрируется на dp.update.
event — Update-объект, пользователя берём прямо из msg.from_user.
"""
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot import logger as log

_log = log.get(__name__)

RATE_SECONDS  = 5.0    # секунд между командами
CLEANUP_EVERY = 500


class CommandThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate_seconds: float = RATE_SECONDS) -> None:
        self._rate:   float            = rate_seconds
        self._last:   dict[int, float] = {}
        self._checks: int              = 0

    def _maybe_cleanup(self) -> None:
        self._checks += 1
        if self._checks % CLEANUP_EVERY:
            return
        cutoff     = time.monotonic() - self._rate * 20
        self._last = {uid: ts for uid, ts in self._last.items() if ts > cutoff}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event:   TelegramObject,
        data:    dict[str, Any],
    ) -> Any:
        msg = getattr(event, "message", None)
        if not msg or not msg.text or not msg.text.startswith("/"):
            return await handler(event, data)

        # берём user_id прямо из объекта Message — не зависим от data
        if not msg.from_user:
            return await handler(event, data)
        user_id = msg.from_user.id

        self._maybe_cleanup()

        now     = time.monotonic()
        last    = self._last.get(user_id, 0.0)
        elapsed = now - last

        if elapsed < self._rate:
            wait = round(self._rate - elapsed, 1)
            _log.info("throttle: user=%s cmd=%s wait=%.1fs", user_id, msg.text.split()[0], wait)
            try:
                await msg.answer(f"⏳  {wait}с.")
            except Exception:
                pass
            return          # глотаем апдейт, handler не вызываем

        self._last[user_id] = now
        return await handler(event, data)