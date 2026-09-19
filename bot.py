import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, LabeledPrice, PreCheckoutQuery

from db import Database
from search_engine import generate_and_check, get_last_error

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
        "✨ <b>Добро пожаловать в MonoSearch</b> ✨\n\n"
        "💎 <i>Интеллектуальный подбор драгоценных свободных юзернеймов в Coregram.</i>\n\n"
        "⚙️ <b>Гибкая настройка:</b> выберите длину и желаемое количество результатов.",
        reply_markup=menu(user.id),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "home")
async def home(call: CallbackQuery):
    user = call.from_user
    db.ensure_user(user.id, user.username)
    await call.message.edit_text(
        "✨ <b>MonoSearch Главное меню</b> ✨\n\n"
        "🎯 Выберите нужное действие на панели ниже:",
        reply_markup=menu(user.id),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "categories")
async def categories_handler(call: CallbackQuery):
    await call.message.edit_text(
        "📂 <b>Шаг 1 из 2: Выберите длину юзернейма</b>\n\n"
        "<i>Короткие категории (4 и 5 букв) требуют Premium-статуса. Остальные доступны бесплатно.</i>",
        reply_markup=length_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("len:"))
async def select_count_handler(call: CallbackQuery):
    length_val = call.data.split(":")[1]
    user = call.from_user
    db.ensure_user(user.id, user.username)

    # Проверка для премиум категорий (4 и 5 букв)
    if length_val in ["4", "5"]:
        if not (is_admin(user.id) or db.is_premium(user.id)):
            await call.message.edit_text(
                "⭐ <b>Доступ ограничен</b>\n\n"
                f"Категория <b>{length_val} буквы</b> является премиальной и доступна только обладателям Premium-статуса.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Получить Premium", callback_data="premium")],
                    [InlineKeyboardButton(text="« Назад к длине", callback_data="categories")],
                ]),
                parse_mode="HTML",
            )
            await call.answer()
            return

    label_text = f"{length_val} букв" if length_val != "8_10" else "8-10 букв"
    await call.message.edit_text(
        f"📊 <b>Шаг 2 из 2: Выберите количество</b>\n\n"
        f"Вы выбрали длину: <b>{label_text}</b>.\n"
        "Сколько свободных вариантов вы хотите получить?",
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

    # Проверка лимитов бесплатных запросов
    if not is_admin(user.id) and not db.is_premium(user.id):
        if not db.consume_request(user.id):
            await call.message.edit_text(
                "⚡ <b>Лимит бесплатных запросов исчерпан</b>\n\n"
                "На сегодня доступно 3 бесплатных поиска.",
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
        f"⚙️ <b>Ищем {count} свободных юзов ({length_val} символов)...</b>\n\n"
        "⏳ <i>Генерируем благозвучные слова и проверяем через Coregram...</i>",
        parse_mode="HTML",
    )
    
    found = await generate_and_check(target=count, length_option=length_option)
    db.add_search(user.id, count, len(found))

    if not found:
        debug_info = get_last_error()
        text = (
            "⚠️ <b>Ничего не удалось найти</b>\n\n"
            f"🛠 <b>Ответ сервера Coregram:</b>\n<code>{debug_info}</code>\n\n"
            "Нажмите кнопку ниже, чтобы попробовать снова."
        )
    else:
        # Вывод обычным текстом без моноширинных блоков
        label_text = f"{length_val} букв" if length_val != "8_10" else "8-10 букв"
        lines = [
            f"💎 <b>Свободные драгоценные юзы ({label_text}):</b>",
            ""
        ]
        lines.extend(f"• @{u}" for u in found)
        text = "\n".join(lines)

    await call.message.edit_text(text, reply_markup=result_menu(), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Недостаточно прав!", show_alert=True)
        return
    users = db.get_all_users()
    await call.message.edit_text(
        "👑 <b>Панель Администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{len(users)}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Управление пользователями", callback_data="admin:users")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data == "admin:users")
async def admin_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    users = db.get_all_users()
    keyboard = []
    for u in users[:20]:
        uid, username, extra, prem, banned = u
        uname = f"@{username}" if username else f"ID: {uid}"
        icon = "🔴" if banned else ("👑" if is_admin(uid) else ("⭐" if prem > time_now_safe() else "👤"))
        keyboard.append([InlineKeyboardButton(text=f"{icon} {uname}", callback_data=f"admin:user:{uid}")])
    keyboard.append([InlineKeyboardButton(text="« Назад", callback_data="admin_panel")])
    await call.message.edit_text("👥 <b>Пользователи:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[2])
    user_data = db.get_user(target_id)
    if not user_data:
        await call.answer("Пользователь не найден!", show_alert=True)
        return
    uid, username, extra, prem, banned = user_data
    uname = f"@{username}" if username else f"ID: {uid}"
    status = "🔴 Заблокирован" if banned else ("👑 Админ" if is_admin(uid) else ("⭐ Premium" if prem > time_now_safe() else "👤 Обычный"))
    text = f"👤 <b>Пользователь:</b> {uname}\n🆔 <code>{uid}</code>\n💎 Статус: <b>{status}</b>"
    keyboard = [
        [InlineKeyboardButton(text="⭐ Премиум на 30 дней", callback_data=f"admin:act:prem:30:{uid}")],
        [InlineKeyboardButton(text="🔨 Бан / 🔓 Разбан", callback_data=f"admin:act:ban:{uid}")],
        [InlineKeyboardButton(text="« К списку", callback_data="admin:users")],
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("admin:act:"))
async def admin_action(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split(":")
    action = parts[2]
    if action == "prem":
        days, target_id = int(parts[3]), int(parts[4])
        db.add_premium(target_id, days)
        await call.answer("✅ Премиум выдан!", show_alert=True)
    elif action == "ban":
        target_id = int(parts[3])
        db.toggle_ban(target_id)
        await call.answer("✅ Статус изменен!", show_alert=True)
    await call.answer()

def time_now_safe():
    return int(datetime.now(timezone.utc).timestamp())

@router.callback_query(F.data == "premium")
async def premium(call: CallbackQuery):
    await call.message.edit_text(
        "⭐ <b>MonoSearch Premium</b> ⭐\n\n"
        "💎 Доступ к эксклюзивным категориям (4 и 5 букв)\n"
        "🚀 Безлимитные поиски без ограничений\n\n"
        "👇 Выберите срок подписки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="7 дней — 49 ⭐", callback_data="buy_premium:7:49")],
            [InlineKeyboardButton(text="30 дней — 129 ⭐", callback_data="buy_premium:30:129")],
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
        description=f"Подписка на {days} дней",
        payload=f"premium:{days}",
        currency="XTR",
        prices=[LabeledPrice(label=f"Premium {days} дней", amount=int(stars))],
    )
    await call.answer()

@router.callback_query(F.data == "packs")
async def packs(call: CallbackQuery):
    await call.message.edit_text(
        "📦 <b>Пакеты запросов</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="10 запросов — 30 ⭐", callback_data="buy_pack:10:30")],
            [InlineKeyboardButton(text="50 запросов — 120 ⭐", callback_data="buy_pack:50:120")],
            [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("buy_pack:"))
async def buy_pack(call: CallbackQuery):
    _, amount, stars = call.data.split(":")
    await call.message.answer_invoice(
        title="Пакет запросов",
        description=f"Набор из {amount} поисков",
        payload=f"pack:{amount}",
        currency="XTR",
        prices=[LabeledPrice(label=f"{amount} поисков", amount=int(stars))],
    )
    await call.answer()

@router.callback_query(F.data == "support")
async def support(call: CallbackQuery):
    await call.message.edit_text(
        "❤️ <b>Поддержать проект</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⭐ 25", callback_data="support:25"),
             InlineKeyboardButton(text="⭐ 50", callback_data="support:50"),
             InlineKeyboardButton(text="⭐ 100", callback_data="support:100")],
            [InlineKeyboardButton(text="« Назад", callback_data="home")],
        ]),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("support:"))
async def buy_support(call: CallbackQuery):
    stars = int(call.data.split(":")[1])
    await call.message.answer_invoice(
        title="Поддержка проекта",
        description="Вклад в развитие сервиса",
        payload=f"support:{stars}",
        currency="XTR",
        prices=[LabeledPrice(label="Поддержка", amount=stars)],
    )
    await call.answer()

@router.callback_query(F.data == "history")
async def history(call: CallbackQuery):
    rows = db.history(call.from_user.id)
    if not rows:
        text = "📌 <b>История поисков пуста.</b>"
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
        "ℹ️ <b>Справка</b>\n\nВыберите категорию нужной длины и количество результатов в меню поиска.",
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
        await message.answer(f"⭐ Premium подписка на {days} дней активирована!")
    elif payload.startswith("pack:"):
        amount = int(payload.split(":")[1])
        db.add_requests(message.from_user.id, amount)
        await message.answer(f"📦 Начислено поисков: {amount}.")
    elif payload.startswith("support:"):
        await message.answer("❤️ Спасибо за поддержку!")

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
    print("Бот с гибким выбором длины и количества запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
