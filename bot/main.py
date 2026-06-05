import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from db.session import engine
from db.models import Base
from bot.middlewares.session import SessionMiddleware, BanCheckMiddleware
from bot.handlers import start, browse, profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot) -> None:
    # Создаём таблицы (в продакшене использовать Alembic)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ready.")

    if settings.use_webhook:
        url = f"{settings.webhook_host}{settings.webhook_path}"
        await bot.set_webhook(url)
        logger.info(f"Webhook set: {url}")


async def on_shutdown(bot: Bot) -> None:
    if settings.use_webhook:
        await bot.delete_webhook()
    await engine.dispose()
    logger.info("Bot stopped.")


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Middleware (порядок важен)
    dp.update.middleware(SessionMiddleware())
    dp.update.middleware(BanCheckMiddleware())

    # Роутеры
    dp.include_router(start.router)
    dp.include_router(browse.router)
    dp.include_router(profile.router)

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    if settings.use_webhook:
        from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
        from aiohttp import web

        app = web.Application()
        SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.webhook_path)
        setup_application(app, dp, bot=bot)
        web.run_app(app, port=settings.webhook_port)
    else:
        logger.info("Starting polling...")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())
