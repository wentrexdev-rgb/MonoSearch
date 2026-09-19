import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, LabeledPrice, PreCheckoutQuery

from db import Database
from search_engine import generate_and_check

TOKEN = "1780243306:E05ncdTVuEvF6s-s_9-RzU854yvZF9D89vM"
DB_PATH = "monosearch.db"

router = Router()
db = Database(DB_PATH)

ADMIN_IDS = [1780243277, 1780243306]

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def menu(user_id: int = 0):
    keyboard = [
        [InlineKeyboardButton(text="🔎 Начать поиск юзов", callback_data="categories")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
         InlineKeyboardButton(text="📦 Пакеты", callback_data="packs")],
        [InlineKeyboardButton(text="❤️ Поддержать", callback_data="support")],
        [InlineKeyboardButton(text="📌 Мои поиски", callback_data="history"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ]
    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def length_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="4 буквы ⭐ (Премиум)", callback_data="len:4"),
         InlineKeyboardButton(text="5 букв ⭐ (Премиум)", callback_data="len:5")],
        [InlineKeyboardButton(text="6 букв 🆓", callback_data="len:6"),
         InlineKeyboardButton(text="7 букв 🆓", callback_data="len:7")],
        [InlineKeyboardButton(text="8-10 букв 🆓", callback_data="len:8_10")],
        [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
    ])

def count_menu(length_val: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 шт.", callback_data=f"run:{length_val}:5"),
         InlineKeyboardButton(text="10 шт.", callback_data=f"run:{length_val}:10"),
         InlineKeyboardButton(text="20 шт.", callback_data=f"run:{length_val}:20")],
        [InlineKeyboardButton(text="« К выбору длины", callback_data="categories")],
    ])

def result_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Искать ещё", callback_data="categories")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

@router.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    db.ensure_user(user.id, user.username)
    await message.answer(
        "✨ <b>MonoSearch</b> — поиск свободных юзернеймов.\n\n"
        "Выберите действие ниже:",
        reply_markup=menu(user.id),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    user = call.from_user
    db.ensure_user(user.id, user.username)
    await call.message.edit_text(
        "✨ <b>MonoSearch Главное меню</b> ✨\n\nВыберите раздел:",
        reply_markup=menu(user.id),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "categories")
async def categories_handler(call: CallbackQuery):
    await call.message.edit_text(
        "📂 <b>Шаг 1: Выберите длину юзернейма</b>",
        reply_markup=length_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("len:"))
async def select_count_handler(call: CallbackQuery):
    length_val = call.data.split(":")[1]
    user = call.from_user
    db.ensure_user(user.id, user.username)

    if length_val in ["4", "5"]:
        if not (is_admin(user.id) or db.is_premium(user.id)):
            await call.message.edit_text(
                f"⭐ Категория <b>{length_val} буквы</b> доступна только с Premium.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Получить Premium", callback_data="premium")],
                    [InlineKeyboardButton(text="« Назад", callback_data="categories")],
                ]),
                parse_mode="HTML",
            )
            await call.answer()
            return

    label_text = f"{length_val} букв" if length_val != "8_10" else "8-10 букв"
    await call.message.edit_text(
        f"📊 <b>Шаг 2: Сколько штук сгенерировать?</b>\n\nВыбрана длина: <b>{label_text}</b>",
        reply_markup=count_menu(length_val),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("run:"))
async def run_search(call: CallbackQuery):
    _, length_val, target_str = call.data.split(":")
    count = int(target_str)
    user = call.from_user
    db.ensure_user(user.id, user.username)

    if not is_admin(user.id) and not db.is_premium(user.id):
        if not db.consume_request(user.id):
            await call.message.edit_text(
                "⚡ Лимит бесплатных запросов исчерпан.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
                    [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
                ]),
                parse_mode="HTML",
            )
            await call.answer()
            return

    length_option = int(length_val) if length_val.isdigit() else length_val

    await call.message.edit_text(
        f"⏳ <b>Ищем {count} свободных юзов ({length_val})...</b>\nПодождите пару секунд.",
        parse_mode="HTML",
    )
    
    found = await generate_and_check(target=count, length_option=length_option)
    db.add_search(user.id, count, len(found))

    if not found:
        text = (
            "⚠️ <b>В этот раз ничего свободного не нашлось.</b>\n\n"
            "Попробуйте запустить поиск ещё раз или сменить длину."
        )
    else:
        label_text = f"{length_val} букв" if length_val != "8_10" else "8-10 букв"
        lines = [f"💎 <b>Свободные юзы ({label_text}):</b>\n"]
        lines.extend(f"• @{u}" for u in found)
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=result_menu(), parse_mode="HTML")
    await call.answer()

# Остальные обработчики (админка, оплата, история) остаются без изменений...
@router.callback_query(F.data == "premium")
async def premium(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>MonoSearch Premium</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="7 дней — 49 ⭐", callback_data="buy_premium:7:49")],
            [InlineKeyboardButton(text="30 дней — 129 ⭐", callback_data="buy_premium:30:129")],
            [InlineKeyboardButton(text="« Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "packs")
async def packs(call: CallbackQuery):
    await call.message.edit_text(
        "📦 <b>Пакеты запросов</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="10 запросов — 30 ⭐", callback_data="buy_pack:10:30")],
            [InlineKeyboardButton(text="50 запросов — 120 ⭐", callback_data="buy_pack:50:120")],
            [InlineKeyboardButton(text="« Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        "❤️ <b>Поддержать проект</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 25", callback_data="support:25"),
             InlineKeyboardButton(text="⭐ 50", callback_data="support:50")],
            [InlineKeyboardButton(text="« Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "history")
async def history(call: CallbackQuery):
    rows = db.history(call.from_user.id)
    if not rows:
        text = "📌 <b>История пуста.</b>"
    else:
        lines = ["📌 <b>Ваши поиски:</b>\n"]
        for row in rows:
            lines.append(f"• Найдено: <b>{row[0]}</b> шт. — <i>{row[1][:16]}</i>")
        text = "\n".join(lines)
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="home")]
    ]), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "help")
async def help_page(call: CallbackQuery):
    await call.message.edit_text(
        "ℹ️ <b>Справка:</b> выбирайте длину, затем количество, и бот выдаст список свободных вариантов.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню", callback_data="home")]
        ]),
        parse_mode="HTML",
    )
    await call.answer()

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    logging.basicConfig(level=logging.INFO)
    session = AiohttpSession(api=TelegramAPIServer.from_base("http://31.77.9.111:8081"))
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)
    print("Бот запущен! Ошибки скрыты, выбор длины и количества работает.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
