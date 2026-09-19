import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, LabeledPrice, PreCheckoutQuery

from db import Database
from search_engine import generate_and_check

TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DATABASE_PATH", "monosearch.db")

router = Router()
db = Database(DB_PATH)

RESULT_OPTIONS = [5, 10, 20, 50]

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Найти usernames", callback_data="search")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
         InlineKeyboardButton(text="📦 Запросы", callback_data="packs")],
        [InlineKeyboardButton(text="❤️ Поддержать", callback_data="support")],
        [InlineKeyboardButton(text="📌 Мои поиски", callback_data="history"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ])

def count_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5", callback_data="count:5"),
         InlineKeyboardButton(text="10", callback_data="count:10"),
         InlineKeyboardButton(text="20", callback_data="count:20")],
        [InlineKeyboardButton(text="50", callback_data="count:50")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
    ])

def result_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё", callback_data="search")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

@router.message(CommandStart())
async def start(message: Message):
    db.ensure_user(message.from_user.id)
    await message.answer(
        "🔎 <b>MonoSearch</b>\n\n"
        "Умный поиск свободных Telegram usernames.\n\n"
        "Ничего вводить не нужно — я сам сгенерирую кандидатов, "
        "отберу самые удачные и проверю их доступность.\n\n"
        "🆓 Бесплатно: 3 поиска в день\n"
        "⭐ Premium: расширенный поиск\n"
        "⚡ Дополнительные запросы за Stars.",
        reply_markup=menu(),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    await call.message.edit_text(
        "🔎 <b>MonoSearch</b>\n\n"
        "Нажми поиск — я сам подберу готовые usernames.\n\n"
        "🆓 Бесплатно: 3 поиска в день\n"
        "⭐ Premium: расширенный поиск",
        reply_markup=menu(),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "search")
async def search(call: CallbackQuery):
    await call.message.edit_text(
        "🔎 <b>Сколько usernames найти?</b>\n\n"
        "Ничего больше настраивать не нужно.\n"
        "MonoSearch сам смешает разные алгоритмы генерации.",
        reply_markup=count_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("count:"))
async def run_search(call: CallbackQuery):
    count = int(call.data.split(":")[1])
    user_id = call.from_user.id

    db.ensure_user(user_id)
    if db.is_premium(user_id):
        allowed = True
    else:
        allowed = db.consume_request(user_id)

    if not allowed:
        await call.message.edit_text(
            "⚡ <b>Лимит бесплатных поисков закончился.</b>\n\n"
            "Доступно 3 поиска в день.\n"
            "Можно купить дополнительные запросы или Premium.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Купить запросы", callback_data="packs")],
                [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
                [InlineKeyboardButton(text="🏠 Меню", callback_data="home")],
            ]),
            parse_mode="HTML",
        )
        await call.answer()
        return

    await call.message.edit_text(
        "🧠 <b>Генерирую...</b>\n\n"
        "Создаю много разных кандидатов → фильтрую → "
        "оцениваю звучание → проверяю доступность.",
        parse_mode="HTML",
    )
    found = await generate_and_check(count)

    db.add_search(user_id, count, len(found))

    if not found:
        text = (
            "🔎 <b>Ничего не найдено</b>\n\n"
            "В этот раз свободных подходящих вариантов не оказалось. "
            "Попробуй ещё раз — генератор каждый раз создаёт новую выборку."
        )
    else:
        lines = [
            "🔎 <b>Готово</b>",
            "",
            f"Найдено свободных: <b>{len(found)}</b>",
            "",
        ]
        lines.extend(f"🟢 @{u}" for u in found)
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=result_menu(), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "premium")
async def premium(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>MonoSearch Premium</b>\n\n"
        "💎 Расширенный генератор\n"
        "⚡ Без дневного лимита бесплатных поисков\n"
        "🧠 Больше кандидатов и более строгая сортировка\n"
        "🔔 Возможность будущего мониторинга usernames\n\n"
        "Выбери срок:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="7 дней — 49 ⭐", callback_data="buy_premium:7:49")],
            [InlineKeyboardButton(text="30 дней — 129 ⭐", callback_data="buy_premium:30:129")],
            [InlineKeyboardButton(text="90 дней — 299 ⭐", callback_data="buy_premium:90:299")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("buy_premium:"))
async def buy_premium(call: CallbackQuery):
    _, days, stars = call.data.split(":")
    await call.message.answer_invoice(
        title="MonoSearch Premium",
        description=f"Premium на {days} дней",
        payload=f"premium:{days}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {days} дней", amount=int(stars))],
    )
    await call.answer()

@router.callback_query(F.data == "packs")
async def packs(call: CallbackQuery):
    await call.message.edit_text(
        "📦 <b>Дополнительные поиски</b>\n\n"
        "Эти пакеты добавляют запросы сверх бесплатного лимита.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="3 запроса — 3 ⭐", callback_data="buy_pack:3:3")],
            [InlineKeyboardButton(text="10 запросов — 30 ⭐", callback_data="buy_pack:10:30")],
            [InlineKeyboardButton(text="25 запросов — 65 ⭐", callback_data="buy_pack:25:65")],
            [InlineKeyboardButton(text="50 запросов — 120 ⭐", callback_data="buy_pack:50:120")],
            [InlineKeyboardButton(text="100 запросов — 220 ⭐", callback_data="buy_pack:100:220")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("buy_pack:"))
async def buy_pack(call: CallbackQuery):
    _, amount, stars = call.data.split(":")
    await call.message.answer_invoice(
        title="MonoSearch — запросы",
        description=f"{amount} дополнительных поисков",
        payload=f"pack:{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} поисков", amount=int(stars))],
    )
    await call.answer()

@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    buttons = []
    for stars in [15, 25, 50, 100, 200, 350]:
        buttons.append(InlineKeyboardButton(text=f"⭐ {stars}", callback_data=f"support:{stars}"))
    await call.message.edit_text(
        "❤️ <b>Поддержать MonoSearch</b>\n\n"
        "Если сервис оказался полезным, можно поддержать проект Stars.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            buttons[:3], buttons[3:],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("support:"))
async def buy_support(call: CallbackQuery):
    stars = int(call.data.split(":")[1])
    await call.message.answer_invoice(
        title="Поддержка MonoSearch",
        description="Добровольная поддержка проекта",
        payload=f"support:{stars}",
        currency="XTR",
        prices=[LabeledPrice(label="Поддержка", amount=stars)],
    )
    await call.answer()

@router.callback_query(F.data == "history")
async def history(call: CallbackQuery):
    rows = db.history(call.from_user.id)
    if not rows:
        text = "📌 <b>Мои поиски</b>\n\nИстория пока пустая."
    else:
        lines = ["📌 <b>Мои поиски</b>", ""]
        for row in rows:
            lines.append(f"• {row[0]} результатов — {row[1]}")
        text = "\n".join(lines)
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Меню", callback_data="home")]
    ]), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "help")
async def help_page(call: CallbackQuery):
    await call.message.edit_text(
        "ℹ️ <b>Как работает MonoSearch</b>\n\n"
        "Ты не вводишь слово и не задаёшь шаблон.\n"
        "Генератор сам создаёт множество новых вариантов, "
        "оценивает их по читаемости и брендируемости, удаляет мусор "
        "и проверяет кандидатов через Telegram.\n\n"
        "Проверка доступности является best-effort: Telegram не предоставляет "
        "обычному Bot API простой универсальный метод проверки username.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Меню", callback_data="home")]
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    if payload.startswith("premium:"):
        days = int(payload.split(":")[1])
        db.add_premium(message.from_user.id, days)
        await message.answer(f"⭐ Premium активирован на {days} дней.")
    elif payload.startswith("pack:"):
        amount = int(payload.split(":")[1])
        db.add_requests(message.from_user.id, amount)
        await message.answer(f"📦 Добавлено запросов: {amount}.")
    elif payload.startswith("support:"):
        await message.answer("❤️ Спасибо за поддержку MonoSearch!")

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    logging.basicConfig(level=logging.INFO)
    bot = Bot(TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
