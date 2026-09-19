import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, LabeledPrice, PreCheckoutQuery

from db import Database
from search_engine import generate_and_check

TOKEN = os.getenv("BOT_TOKEN", "")
DB_PATH = os.getenv("DATABASE_PATH", "monosearch.db")

router = Router()
db = Database(DB_PATH)

ADMIN_USERNAME = "dick"

def is_admin(username: str) -> bool:
    if not username:
        return False
    return username.lower() == ADMIN_USERNAME.lower()

def menu(user_username: str = ""):
    keyboard = [
        [InlineKeyboardButton(text="🔎 Найти usernames", callback_data="search")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
         InlineKeyboardButton(text="📦 Запросы", callback_data="packs")],
        [InlineKeyboardButton(text="❤️ Поддержать", callback_data="support")],
        [InlineKeyboardButton(text="📌 Мои поиски", callback_data="history"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ]
    if is_admin(user_username):
        keyboard.insert(0, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def count_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="5 шт.", callback_data="count:5"),
         InlineKeyboardButton(text="10 шт.", callback_data="count:10"),
         InlineKeyboardButton(text="20 шт.", callback_data="count:20")],
        [InlineKeyboardButton(text="50 шт.", callback_data="count:50")],
        [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
    ])

def result_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Искать ещё", callback_data="search")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])

@router.message(CommandStart())
async def start(message: Message):
    user = message.from_user
    db.ensure_user(user.id, user.username)
    
    await message.answer(
        "✨ <b>Добро пожаловать в MonoSearch</b> ✨\n\n"
        "🚀 <i>Интеллектуальный генератор и отборщик свободных Telegram usernames.</i>\n\n"
        "💡 <b>Как это работает?</b>\n"
        "Вам не нужно вводить ключевые слова. Алгоритм сам создает уникальные фонетические комбинации, отсеивает мусор и проверяет их доступность в реальном времени.\n\n"
        "📊 <b>Ваши лимиты:</b>\n"
        "• 🆓 Бесплатно: <b>3 поиска</b> в день\n"
        "• ⭐ Premium: <b>безлимит</b> + расширенная фильтрация\n"
        "• ⚡ Дополнительные пакеты запросов за Telegram Stars",
        reply_markup=menu(user.username),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    user = call.from_user
    db.ensure_user(user.id, user.username)
    await call.message.edit_text(
        "✨ <b>MonoSearch Главное меню</b> ✨\n\n"
        "🎯 Выберите нужное действие на панели ниже:",
        reply_markup=menu(user.username),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "search")
async def search(call: CallbackQuery):
    await call.message.edit_text(
        "🔍 <b>Параметры поиска</b>\n\n"
        "Выберите желаемое количество свободных usernames для генерации:",
        reply_markup=count_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("count:"))
async def run_search(call: CallbackQuery):
    count = int(call.data.split(":")[1])
    user = call.from_user
    db.ensure_user(user.id, user.username)

    if is_admin(user.username) or db.is_premium(user.id):
        allowed = True
    else:
        allowed = db.consume_request(user.id)

    if not allowed:
        await call.message.edit_text(
            "⚡ <b>Лимит бесплатных запросов исчерпан</b>\n\n"
            "На сегодня доступно 3 бесплатных поиска.\n"
            "Вы можете приобрести дополнительные пакеты или оформить Premium статус.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📦 Купить запросы", callback_data="packs")],
                [InlineKeyboardButton(text="⭐ Premium", callback_data="premium")],
                [InlineKeyboardButton(text="🏠 В меню", callback_data="home")],
            ]),
            parse_mode="HTML",
        )
        await call.answer()
        return

    await call.message.edit_text(
        "⚙️ <b>Идет интеллектуальный поиск...</b>\n\n"
        "⏳ <i>Генерируем комбинации → проверяем звучание → тестируем доступность в сети... Пожалуйста, подождите.</i>",
        parse_mode="HTML",
    )
    
    found = await generate_and_check(count)
    db.add_search(user.id, count, len(found))

    if not found:
        text = (
            "⚠️ <b>Ничего не удалось найти</b>\n\n"
            "В этот раз свободные варианты не прошли строгий фильтр доступности. "
            "Нажмите «Искать ещё», чтобы запустить генератор повторно."
        )
    else:
        lines = [
            "🎉 <b>Успешно найдено свободных usernames:</b>",
            "",
        ]
        lines.extend(f"🟢 <code>@{u}</code>" for u in found)
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=result_menu(), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if not is_admin(call.from_user.username):
        await call.answer("⛔ Недостаточно прав!", show_alert=True)
        return
    
    await call.message.edit_text(
        "👑 <b>Панель Администратора / Владельца</b>\n\n"
        "Приветствую, босс! Вы вошли в секретное меню управления ботом.\n"
        "Выберите инструмент:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Список всех пользователей", callback_data="admin:users")],
            [InlineKeyboardButton(text="⚡ Выдать запросы игроку", callback_data="admin:give_menu")],
            [InlineKeyboardButton(text="🔨 Забанить / Разбанить", callback_data="admin:ban_menu")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "admin:users")
async def admin_users(call: CallbackQuery):
    if not is_admin(call.from_user.username):
        return
    users = db.get_all_users()
    text = "👥 <b>Список зарегистрированных пользователей:</b>\n\n"
    for u in users:
        uid, username, extra, prem, banned = u
        uname = f"@{username}" if username else f"ID: {uid}"
        status = "🔴 ЗАБАНЕН" if banned else ("⭐ Премиум" if prem > time_now_safe() else "👤 Обычный")
        text += f"• {uname} | Запросов: {extra} | Статус: {status}\n"
    
    if len(text) > 4000:
        text = text[:3996] + "\n..."

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_panel")]
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "admin:give_menu")
async def admin_give_menu(call: CallbackQuery):
    if not is_admin(call.from_user.username):
        return
    await call.message.edit_text(
        "⚡ <b>Выдача запросов пользователю</b>\n\n"
        "Отправьте в чат команду в формате:\n"
        "<code>/give username количество</code>\n"
        "<i>Например: /give username_123 50</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_panel")]
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "admin:ban_menu")
async def admin_ban_menu(call: CallbackQuery):
    if not is_admin(call.from_user.username):
        return
    await call.message.edit_text(
        "🔨 <b>Управление блокировками</b>\n\n"
        "Отправьте в чат команду для бана/разбана:\n"
        "• Бан: <code>/ban username</code>\n"
        "• Разбан: <code>/unban username</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад в админку", callback_data="admin_panel")]
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.message(Command("give"))
async def cmd_give(message: Message):
    if not is_admin(message.from_user.username):
        return
    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Формат: /give username количество")
        return
    target_uname = args[1].lstrip("@")
    try:
        amount = int(args[2])
    except ValueError:
        await message.answer("⚠️ Количество должно быть числом.")
        return
    
    success = db.add_requests_by_username(target_uname, amount)
    if success:
        await message.answer(f"✅ Успешно добавлено {amount} запросов для @{target_uname}!")
    else:
        await message.answer(f"❌ Пользователь @{target_uname} не найден в базе данных.")

@router.message(Command("ban"))
async def cmd_ban(message: Message):
    if not is_admin(message.from_user.username):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Формат: /ban username")
        return
    target_uname = args[1].lstrip("@")
    db.set_ban_by_username(target_uname, 1)
    await message.answer(f"🔨 Пользователь @{target_uname} заблокирован.")

@router.message(Command("unban"))
async def cmd_unban(message: Message):
    if not is_admin(message.from_user.username):
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Формат: /unban username")
        return
    target_uname = args[1].lstrip("@")
    db.set_ban_by_username(target_uname, 0)
    await message.answer(f"🔓 Пользователь @{target_uname} разблокирован.")

def time_now_safe():
    return int(datetime.now(timezone.utc).timestamp())

@router.callback_query(F.data == "premium")
async def premium(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>MonoSearch Premium Статус</b> ⭐\n\n"
        "💎 Безлимитные поиски без ограничений\n"
        "🧠 Улучшенные алгоритмы ранжирования кандидатов\n"
        "🔔 Приоритетная скорость обработки запросов\n\n"
        "👇 Выберите срок подписки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="7 дней — 49 ⭐", callback_data="buy_premium:7:49")],
            [InlineKeyboardButton(text="30 дней — 129 ⭐", callback_data="buy_premium:30:129")],
            [InlineKeyboardButton(text="90 дней — 299 ⭐", callback_data="buy_premium:90:299")],
            [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("buy_premium:"))
async def buy_premium(call: CallbackQuery):
    _, days, stars = call.data.split(":")
    await call.message.answer_invoice(
        title="MonoSearch Premium",
        description=f"Активация подписки Premium на {days} дней",
        payload=f"premium:{days}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {days} дней", amount=int(stars))],
    )
    await call.answer()

@router.callback_query(F.data == "packs")
async def packs(call: CallbackQuery):
    await call.message.edit_text(
        "📦 <b>Пакеты дополнительных запросов</b>\n\n"
        "Выберите подходящий набор поисков для постоянного использования:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="3 запроса — 3 ⭐", callback_data="buy_pack:3:3")],
            [InlineKeyboardButton(text="10 запросов — 30 ⭐", callback_data="buy_pack:10:30")],
            [InlineKeyboardButton(text="25 запросов — 65 ⭐", callback_data="buy_pack:25:65")],
            [InlineKeyboardButton(text="50 запросов — 120 ⭐", callback_data="buy_pack:50:120")],
            [InlineKeyboardButton(text="100 запросов — 220 ⭐", callback_data="buy_pack:100:220")],
            [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("buy_pack:"))
async def buy_pack(call: CallbackQuery):
    _, amount, stars = call.data.split(":")
    await call.message.answer_invoice(
        title="MonoSearch — Пакет запросов",
        description=f"Набор из {amount} поисков",
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
        "❤️ <b>Поддержать развитие проекта</b>\n\n"
        "Если бот помог вам занять крутой юзернейм, вы можете выразить благодарность разработчику через Telegram Stars.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            buttons[:3], buttons[3:],
            [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("support:"))
async def buy_support(call: CallbackQuery):
    stars = int(call.data.split(":")[1])
    await call.message.answer_invoice(
        title="Поддержка MonoSearch",
        description="Добровольный вклад в развитие сервиса",
        payload=f"support:{stars}",
        currency="XTR",
        prices=[LabeledPrice(label="Поддержка проекта", amount=stars)],
    )
    await call.answer()

@router.callback_query(F.data == "history")
async def history(call: CallbackQuery):
    rows = db.history(call.from_user.id)
    if not rows:
        text = "📌 <b>История поисков</b>\n\nВы еще не запускали генерацию."
    else:
        lines = ["📌 <b>Ваши последние поиски:</b>", ""]
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
        "ℹ️ <b>Справка и руководство</b>\n\n"
        "🤖 <b>MonoSearch Bot</b> генерирует качественные буквенные сочетания по фонетическим правилам, проверяя их доступность.\n\n"
        "🛡 <i>Безопасность и конфиденциальность:</i> все операции выполняются автоматически в защищенной среде.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В меню", callback_data="home")]
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
        await message.answer(f"⭐ <b>Успешно!</b> Premium-подстактивация на {days} дней выполнена.")
    elif payload.startswith("pack:"):
        amount = int(payload.split(":")[1])
        db.add_requests(message.from_user.id, amount)
        await message.answer(f"📦 <b>Успешно!</b> Начислено дополнительных поисков: {amount}.")
    elif payload.startswith("support:"):
        await message.answer("❤️ Огромное спасибо за вашу поддержку проекта!")

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    logging.basicConfig(level=logging.INFO)
    session = AiohttpSession(
        api=TelegramAPIServer.from_base("http://31.77.9.111:8081")
    )
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
