from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

_RULES = """\
📜  <b>правила</b>

1.  реальные фото и возраст.  фейки — бан.
2.  уважение.  давление, харасмент, угрозы — бан.
3.  без спама, рекламы и ссылок в анкете.
4.  нашёл неадеквата — жми репорт под анкетой.
5.  за переписку и встречи вне бота мы не несём ответственности.

<i>нарушение любого пункта — бан без предупреждения.</i>"""


@router.message(Command("rules"))
async def cmd_rules(message: Message):
    await message.answer(_RULES, parse_mode="HTML")