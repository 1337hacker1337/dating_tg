"""bot/handlers/user/rules.py — /rules."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.texts import RULES

router = Router(name="rules")


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(RULES, parse_mode="HTML")
