import asyncio, logging, random
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db.session import AsyncSessionFactory
from db.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)
INACTIVE_HOURS      = 48
COOLDOWN_HOURS      = 48
CHECK_INTERVAL_HOURS = 2

_MESSAGES = [
    "🕯️  тебя ждут.\n<i>пока пропадал — кое-что изменилось.</i>",
    "🩸  не забыли.\n<i>загляни в ленту.</i>",
    "👁️  кто-то смотрел.\n<i>зайди и проверь.</i>",
    "🌑  темно без тебя.\n<i>лента скучает.</i>",
]


async def _run_notify_job(bot: Bot) -> None:
    try:
        async with AsyncSessionFactory() as session:
            repo     = UserRepository(session)
            # get_users_for_notify уже фильтрует notifications_enabled=True
            user_ids = await repo.get_users_for_notify(
                inactive_hours=INACTIVE_HOURS,
                cooldown_hours=COOLDOWN_HOURS,
            )
        if not user_ids:
            logger.debug("notify: нет кандидатов")
            return

        logger.info("notify: отправляю %d", len(user_ids))
        ok = fail = 0
        notified  = []
        for uid in user_ids:
            try:
                await bot.send_message(uid, random.choice(_MESSAGES), parse_mode="HTML")
                notified.append(uid)
                ok += 1
            except Exception as e:
                logger.debug("notify fail uid=%s: %s", uid, e)
                fail += 1
            await asyncio.sleep(0.05)

        if notified:
            async with AsyncSessionFactory() as session:
                repo = UserRepository(session)
                await repo.set_notified(notified)
                await session.commit()

        logger.info("notify: ok=%d fail=%d", ok, fail)
    except Exception:
        logger.exception("notify: ошибка")


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        _run_notify_job,
        trigger="interval",
        hours=CHECK_INTERVAL_HOURS,
        args=[bot],
        id="daily_notify",
        replace_existing=True,
    )
    return scheduler