import asyncio
import logging
import os
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import CommandStart
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
    
    users = db.get_all_users()
    await call.message.edit_text(
        "👑 <b>Панель Администратора (Владелец)</b>\n\n"
        f"👥 Всего пользователей в базе: <b>{len(users)}</b>\n"
        "👇 Нажмите кнопку ниже для управления пользователями:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin:users")],
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
    keyboard = []
    for u in users[:20]: # Показываем первые 20 для удобства
        uid, username, extra, prem, banned = u
        uname = f"@{username}" if username else f"ID: {uid}"
        icon = "🔴" if banned else ("⭐" if prem > time_now_safe() else "👤")
        keyboard.append([InlineKeyboardButton(text=f"{icon} {uname} (Доп: {extra})", callback_data=f"admin:user:{uid}")])
    
    keyboard.append([InlineKeyboardButton(text="« Назад в админку", callback_data="admin_panel")])
    
    await call.message.edit_text(
        "👥 <b>Список пользователей:</b>\nВыберите пользователя для управления:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail(call: CallbackQuery):
    if not is_admin(call.from_user.username):
        return
    target_id = int(call.data.split(":")[2])
    user_data = db.get_user(target_id)
    if not user_data:
        await call.answer("Пользователь не найден!", show_alert=True)
        return

    uid, username, extra, prem, banned = user_data
    uname = f"@{username}" if username else f"ID: {uid}"
    status = "🔴 Заблокирован" if banned else ("⭐ Premium активен" if prem > time_now_safe() else "👤 Обычный")

    text = (
        f"👤 <b>Управление пользователем:</b> {uname}\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"⚡ Дополнительных запросов: <b>{extra}</b>\n"
        f"💎 Статус: <b>{status}</b>"
    )

    keyboard = [
        [InlineKeyboardButton(text="➕ Дать +10 запросов", callback_data=f"admin:act:give:10:{uid}"),
         InlineKeyboardButton(text="➕ Дать +50 запросов", callback_data=f"admin:act:give:50:{uid}")],
        [InlineKeyboardButton(text="⭐ Премиум на 30 дней", callback_data=f"admin:act:prem:30:{uid}")],
        [InlineKeyboardButton(text="🔨 Бан / 🔓 Разбан", callback_data=f"admin:act:ban:{uid}")],
        [InlineKeyboardButton(text="« К списку пользователей", callback_data="admin:users")],
    ]

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("admin:act:"))
async def admin_action(call: CallbackQuery):
    if not is_admin(call.from_user.username):
        return
    parts = call.data.split(":")
    action = parts[2]
    
    if action == "give":
        amount = int(parts[3])
        target_id = int(parts[4])
        db.add_requests_by_id(target_id, amount)
        await call.answer(f"✅ Добавлено {amount} запросов!", show_alert=True)
    elif action == "prem":
        days = int(parts[3])
        target_id = int(parts[4])
        db.add_premium(target_id, days)
        await call.answer(f"✅ Премиум выдан на {days} дней!", show_alert=True)
    elif action == "ban":
        target_id = int(parts[3])
        new_status = db.toggle_ban(target_id)
        status_text = "заблокирован 🔴" if new_status == 1 else "разблокирован 🟢"
        await call.answer(f"✅ Пользователь {status_text}!", show_alert=True)

    # Обновляем экран пользователя
    target_id = int(parts[-1])
    user_data = db.get_user(target_id)
    uid, username, extra, prem, banned = user_data
    uname = f"@{username}" if username else f"ID: {uid}"
    status = "🔴 Заблокирован" if banned else ("⭐ Premium активен" if prem > time_now_safe() else "👤 Обычный")

    text = (
        f"👤 <b>Управление пользователем:</b> {uname}\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"⚡ Дополнительных запросов: <b>{extra}</b>\n"
        f"💎 Статус: <b>{status}</b>"
    )
    keyboard = [
        [InlineKeyboardButton(text="➕ Дать +10 запросов", callback_data=f"admin:act:give:10:{uid}"),
         InlineKeyboardButton(text="➕ Дать +50 запросов", callback_data=f"admin:act:give:50:{uid}")],
        [InlineKeyboardButton(text="⭐ Премиум на 30 дней", callback_data=f"admin:act:prem:30:{uid}")],
        [InlineKeyboardButton(text="🔨 Бан / 🔓 Разбан", callback_data=f"admin:act:ban:{uid}")],
        [InlineKeyboardButton(text="« К списку пользователей", callback_data="admin:users")],
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")

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
        await message.answer(f"⭐ <b>Успешно!</b> Premium-подписка на {days} дней активирована.")
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
