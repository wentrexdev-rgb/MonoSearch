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
        [InlineKeyboardButton(text="🔎 Выбрать категорию юзов", callback_data="categories")],
        [InlineKeyboardButton(text="⭐ Premium", callback_data="premium"),
         InlineKeyboardButton(text="📦 Пакеты", callback_data="packs")],
        [InlineKeyboardButton(text="❤️ Поддержать", callback_data="support")],
        [InlineKeyboardButton(text="📌 Мои поиски", callback_data="history"),
         InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ]
    if is_admin(user_id):
        keyboard.insert(0, [InlineKeyboardButton(text="👑 Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def category_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="4 буквы ⭐ (Премиум)", callback_data="cat:4"),
         InlineKeyboardButton(text="5 букв ⭐ (Премиум)", callback_data="cat:5")],
        [InlineKeyboardButton(text="6 букв 🆓 (Бесплатно)", callback_data="cat:6")],
        [InlineKeyboardButton(text="7 букв 🆓 (Бесплатно)", callback_data="cat:7")],
        [InlineKeyboardButton(text="8-10 букв 🆓 (Бесплатно)", callback_data="cat:8_10")],
        [InlineKeyboardButton(text="« Назад в меню", callback_data="home")],
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
        "💎 <i>Генератор премиальных и красивых свободных юзернеймов в Coregram.</i>\n\n"
        "📌 <b>Категории:</b>\n"
        "• 4 и 5 букв — эксклюзивные премиум-варианты ⭐\n"
        "• От 6 до 10 букв — бесплатные качественные юзы 🆓",
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
        "📂 <b>Выберите категорию для поиска:</b>\n\n"
        "<i>Чем короче юзернейм, тем он ценнее. Короткие категории (4-5 букв) требуют Premium-статуса.</i>",
        reply_markup=category_menu(),
        parse_mode="HTML",
    )
    await call.answer()

@router.callback_query(F.data.startswith("cat:"))
async def run_search(call: CallbackQuery):
    data_val = call.data.split(":")[1]
    user = call.from_user
    db.ensure_user(user.id, user.username)

    # Проверка для премиум категорий (4 и 5 букв)
    is_premium_cat = data_val in ["4", "5"]
    
    if is_premium_cat:
        if not (is_admin(user.id) or db.is_premium(user.id)):
            await call.message.edit_text(
                "⭐ <b>Доступ ограничен</b>\n\n"
                f"Категория <b>{data_val} буквы</b> является премиальной и доступна только обладателям Premium-статуса.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="⭐ Получить Premium", callback_data="premium")],
                    [InlineKeyboardButton(text="« Назад к категориям", callback_data="categories")],
                ]),
                parse_mode="HTML",
            )
            await call.answer()
            return

    # Для бесплатных проверяем лимиты запросов
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

    length_option = int(data_val) if data_val.isdigit() else data_val
    
    await call.message.edit_text(
        f"⚙️ <b>Подбираем драгоценные юзы ({data_val} символов)...</b>\n\n"
        "⏳ <i>Генерируем благозвучные слова и проверяем доступность в Coregram...</i>",
        parse_mode="HTML",
    )
    
    # Ищем 10 крутых вариантов
    found = await generate_and_check(target=10, length_option=length_option)
    db.add_search(user.id, 10, len(found))

    if not found:
        debug_info = get_last_error()
        text = (
            "⚠️ <b>Ничего не удалось найти</b>\n\n"
            f"🛠 <b>Ответ сервера Coregram:</b>\n<code>{debug_info}</code>\n\n"
            "Нажмите кнопку ниже, чтобы попробовать снова."
        )
    else:
        # Вывод ОБЫЧНЫМ ТЕКСТОМ без моноширинных блоков
        lines = [
            f"💎 <b>Свободные драгоценные юзы ({data_val} букв):</b>",
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
        "ℹ️ <b>Справка</b>\n\nВыберите категорию нужной длины в главном меню, и бот автоматически отберет для вас красивые свободные варианты.",
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
    print("Бот с гибким выбором категорий запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
