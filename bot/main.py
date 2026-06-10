import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy import text

from bot import logger as log
from bot.notify import create_scheduler
from config import settings
from db.session import engine, AsyncSessionFactory
from db.models import Base
from bot.middlewares.session import SessionMiddleware, BanCheckMiddleware
from bot.middlewares.command_throttle import CommandThrottleMiddleware
from bot.middlewares.subscription import SubscriptionMiddleware
from bot.handlers import start, browse, profile, admin, rules, report, admin_reports

log.setup(log_dir="logs", debug=True)
_log = log.get("bot.main")

_scheduler = None


async def _ensure_first_admin() -> None:
    if not settings.first_admin_id:
        return
    from db.repositories.admin_repo import AdminRepository
    async with AsyncSessionFactory() as session:
        repo = AdminRepository(session)
        if not await repo.is_admin(settings.first_admin_id):
            await repo.add(telegram_id=settings.first_admin_id)
            await session.commit()
            _log.info("первый администратор добавлен: %s", settings.first_admin_id)


async def _run_migrations(conn) -> None:
    """
    Безопасные миграции — добавляем новые колонки если их нет.
    Идемпотентно, работает при каждом запуске.
    """
    migrations = [
        # v2: уведомления on/off
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    ]
    for stmt in migrations:
        await conn.execute(text(stmt))
    _log.info("миграции применены (%d)", len(migrations))


async def on_startup(bot: Bot) -> None:
    global _scheduler
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
    _log.info("БД готова")
    await _ensure_first_admin()
    _scheduler = create_scheduler(bot)
    _scheduler.start()
    _log.info("Планировщик нотифов запущен")
    if settings.use_webhook:
        url = f"{settings.webhook_host}{settings.webhook_path}"
        await bot.set_webhook(url)
        _log.info("Webhook: %s", url)


async def on_shutdown(bot: Bot) -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        _log.info("Планировщик остановлен")
    if settings.use_webhook:
        await bot.delete_webhook()
    await engine.dispose()
    _log.info("Бот остановлен")


async def main() -> None:
    bot = Bot(token=settings.bot_token,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(SessionMiddleware())
    dp.update.middleware(BanCheckMiddleware())
    dp.update.middleware(CommandThrottleMiddleware())  # до subscription
    dp.update.middleware(SubscriptionMiddleware())

    dp.include_router(admin_reports.router)  # раньше admin.router — не зависит от его версии
    dp.include_router(admin.router)
    dp.include_router(rules.router)
    dp.include_router(report.router)
    dp.include_router(start.router)
    dp.include_router(browse.router)
    dp.include_router(profile.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    _log.info("Запуск бота (polling)")

    if settings.use_webhook:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web
        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
        setup_application(app, dp, bot=bot)
        web.run_app(app, port=settings.webhook_port)
    else:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass