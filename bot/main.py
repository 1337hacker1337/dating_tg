"""
bot/main.py — точка входа.

БАГФИКС (webhook): раньше web.run_app() вызывался внутри asyncio.run(),
что роняло процесс с RuntimeError («loop is already running»).
Теперь используется AppRunner/TCPSite в текущем event loop.
"""
import asyncio
import sys
from pathlib import Path

# Запуск как `python bot/main.py` из корня проекта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from sqlalchemy import text

from bot import logger as log
from bot.handlers.admin import router as admin_router
from bot.handlers.user import router as user_router
from bot.middlewares import (
    BanCheckMiddleware,
    CommandThrottleMiddleware,
    SessionMiddleware,
    SubscriptionMiddleware,
)
from bot.services.notify import create_scheduler
from config import settings
from db.models import Base
from db.session import AsyncSessionFactory, engine

_log = log.get(__name__)


# ── Подготовка БД ─────────────────────────────────────────────────

async def _run_migrations() -> None:
    """
    Идемпотентные миграции «на коленке» для существующих инсталляций.
    Для серьёзных изменений схемы — alembic (см. README).
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
            "notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE"
        ))
    _log.info("db ready")


async def _ensure_first_admin() -> None:
    if not settings.first_admin_id:
        return
    from db.repositories.admin_repo import AdminRepository
    async with AsyncSessionFactory() as session:
        repo = AdminRepository(session)
        if not await repo.is_admin(settings.first_admin_id):
            await repo.add(telegram_id=settings.first_admin_id)
            await session.commit()
            _log.info("first admin added: %s", settings.first_admin_id)


# ── Сборка диспетчера ─────────────────────────────────────────────

def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    # Порядок важен: сессия → бан/last_seen → троттлинг → подписка
    dp.update.middleware(SessionMiddleware())
    dp.update.middleware(BanCheckMiddleware())
    dp.update.middleware(CommandThrottleMiddleware())
    dp.update.middleware(SubscriptionMiddleware())

    dp.include_router(admin_router)
    dp.include_router(user_router)
    return dp


# ── Запуск ────────────────────────────────────────────────────────

async def _on_startup(bot: Bot) -> None:
    await _run_migrations()
    await _ensure_first_admin()


async def run_polling() -> None:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    await _on_startup(bot)

    scheduler = create_scheduler(bot)
    scheduler.start()
    _log.info("scheduler started")

    await bot.delete_webhook(drop_pending_updates=True)
    _log.info("polling started")
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()


async def run_webhook() -> None:
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher()
    await _on_startup(bot)

    scheduler = create_scheduler(bot)
    scheduler.start()

    webhook_url = settings.webhook_host.rstrip("/") + settings.webhook_path
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    _log.info("webhook set: %s", webhook_url)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=settings.webhook_port)
    await site.start()
    _log.info("webhook server on :%d", settings.webhook_port)

    try:
        await asyncio.Event().wait()  # работаем до Ctrl+C
    finally:
        scheduler.shutdown(wait=False)
        await runner.cleanup()
        await bot.session.close()


def main() -> None:
    log.setup()
    try:
        if settings.use_webhook:
            asyncio.run(run_webhook())
        else:
            asyncio.run(run_polling())
    except (KeyboardInterrupt, SystemExit):
        _log.info("stopped")


if __name__ == "__main__":
    main()
