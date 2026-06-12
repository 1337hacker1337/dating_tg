from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

_RULES = """\
📜  <b>правила</b>

веди себя как хочешь — но есть три вещи которые не пройдут:

🚫  реклама и спам в анкете или в чате
🚫  запрещённый контент (наркота, оружие и прочее)
🚫  18+ в фотографиях анкеты

всё остальное — твои дела.
репорт на нарушителей — кнопка 🚩 под анкетой.

<i>за нарушение — бан.</i>"""


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(_RULES, parse_mode="HTML")