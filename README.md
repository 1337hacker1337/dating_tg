# SHROOM — Telegram-бот знакомств

aiogram 3 · SQLAlchemy 2 (async) · PostgreSQL · APScheduler · Telegram Stars

## Запуск

```bash
pip install -r requirements.txt
cp .env.example .env      # заполнить BOT_TOKEN, DATABASE_URL, FIRST_ADMIN_ID
python bot/main.py
```

Таблицы и недостающие колонки создаются автоматически при старте.
Для эволюции схемы в проде рекомендуется перейти на alembic (он уже в requirements).

## Структура

```
config.py                  настройки (.env, pydantic-settings)
bot/
  main.py                  точка входа: polling / webhook
  constants.py             лимиты и общие константы (единый источник правды)
  texts.py                 длинные тексты (правила, нотификации)
  states.py                все FSM-состояния
  logger.py                логирование (консоль + файл)
  keyboards/               user.py, admin.py
  middlewares/             session, ban_check, throttle, subscription, admin_guard
  handlers/
    user/                  start, browse, profile, report, rules
    admin/                 panel, users, broadcast, ads, reports
  services/                profile, browse, notify (бизнес-логика)
  utils/                   geo, rating, formatting
db/
  models.py                ORM-модели
  session.py               engine + session factory
  repositories/            user, like/match, admin, settings, report
```

## Исправленные баги

| # | Где | Что было |
|---|-----|----------|
| 1 | `bot/main.py` | `web.run_app()` внутри `asyncio.run()` → падение webhook-режима с RuntimeError. Заменено на `AppRunner`/`TCPSite`. |
| 2 | `handlers/user/profile.py` | Хэндлер редактирования без фильтра перехватывал геолокацию — обновить гео через «✏️ редактировать» было невозможно. Добавлен `F.text`, location-хэндлер объявлен раньше. |
| 3 | `middlewares/subscription.py`, `ban_check.py` | Платёжные апдейты (`pre_checkout_query`, `successful_payment`) глотались проверкой подписки/бана → платёж Stars зависал, либо деньги списывались без удаления анкеты. Добавлен bypass. |
| 4 | `handlers/user/browse.py` | При мэтче партнёру отправлялась карточка с принудительно обнулённым username — кнопка «написать» всегда вела в тупик. |
| 5 | `handlers/admin/reports.py` | Бан по репорту шёл по offset страницы, а не по id — при параллельной работе двух админов можно было забанить не того / молча ничего не сделать. Теперь `get_by_id` + проверка `is_reviewed`. |
| 6 | `keyboards/admin.py` | Раскладка кнопок репортов ломалась на первой/последней странице (считалось `min(3, total)` вместо фактического числа кнопок). |
| 7 | `middlewares/ban_check.py` | username сохранялся один раз при регистрации и не обновлялся — после смены ника кнопка «написать» у мэтчей умирала. Теперь синхронизируется при каждом апдейте. |
| 8 | `constants.py` | Лимит имени: 16 при регистрации, 64 при редактировании. Унифицирован (`NAME_MAX_LEN = 16`). |
| 9 | `handlers/admin/users.py` | Поле `added_by` при добавлении админа всегда оставалось NULL. Теперь заполняется. |
| 10 | — | Удалён мёртвый код: `db/repositories/rating_repo.py` (импортировал несуществующую модель `Rating`), дубликат `bot/admin.py`. |

## Что ещё изменилось (clean code)

- Монолитные `handlers.py` / `admin.py` / `services.py` разрезаны по зонам ответственности.
- Константы, дублировавшиеся в 3–4 файлах (лимиты свайпов, причины репортов, payload платежа), сведены в `bot/constants.py`.
- Длинные тексты вынесены в `bot/texts.py`.
- `AdminMiddleware` подключается один раз на родительский админ-роутер.
- Форматирование карточек анкет (`profile_caption`, `own_profile_text`) — в одном месте (`bot/utils/formatting.py`).
