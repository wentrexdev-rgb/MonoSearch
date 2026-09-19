import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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

# FSM Состояния для админ-панели
class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_requests_count = State()
    waiting_for_premium_days = State()

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
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    db.ensure_user(user.id, user.username)
    if db.is_banned(user.id):
        await message.answer("⛔ Вы заблокированы в этом боте.")
        return
    await message.answer(
        "✨ <b>MonoSearch</b> — поиск свободных юзернеймов.\n\n"
        "Выберите действие ниже:",
        reply_markup=menu(user.id),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "home")
async def home(call: CallbackQuery, state: FSMContext):
    await state.clear()
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

    # АНИМАЦИЯ ПОИСКА: динамическое изменение текста
    await call.message.edit_text("⚙️ <b>Этап 1/3:</b> Генерация пула вариантов...", parse_mode="HTML")
    await asyncio.sleep(0.4)
    await call.message.edit_text("🧠 <b>Этап 2/3:</b> Оценка качества и брендовости...", parse_mode="HTML")
    await asyncio.sleep(0.4)
    await call.message.edit_text(f"🌐 <b>Этап 3/3:</b> Проверка через Coregram API...", parse_mode="HTML")
    
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

# --- УЛУЧШЕННАЯ АДМИН-ПАНЕЛЬ ---

@router.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔ Недостаточно прав!", show_alert=True)
        return
    await state.clear()
    total_users, prem_users, banned_users, total_searches = db.get_stats()
    text = (
        "👑 <b>Панель Администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{total_users}</b>\n"
        f"⭐ Активных Premium: <b>{prem_users}</b>\n"
        f"🔴 Заблокированных: <b>{banned_users}</b>\n"
        f"🔍 Всего поисков выполнено: <b>{total_searches}</b>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin:users")],
        [InlineKeyboardButton(text="🔍 Найти/Ууправлять по ID", callback_data="admin:find_user_prompt")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
    ])
    await call.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "admin:users")
async def admin_users(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    users = db.get_all_users()
    keyboard = []
    for u in users[:25]:
        uid, username, extra, prem, banned = u
        uname = f"@{username}" if username else f"ID: {uid}"
        icon = "🔴" if banned else ("👑" if is_admin(uid) else ("⭐" if prem > int(datetime.now(timezone.utc).timestamp()) else "👤"))
        keyboard.append([InlineKeyboardButton(text=f"{icon} {uname} (ID: {uid})", callback_data=f"admin:user:{uid}")])
    keyboard.append([InlineKeyboardButton(text="« Назад", callback_data="admin_panel")])
    await call.message.edit_text("👥 <b>Пользователи базы:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "admin:find_user_prompt")
async def admin_find_user_prompt(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return
    await state.set_state(AdminState.waiting_for_user_id)
    await call.message.edit_text(
        "🆔 <b>Введите Telegram ID пользователя</b> для управления им:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data="admin_panel")]]),
        parse_mode="HTML",
    )
    await call.answer()

@router.message(AdminState.waiting_for_user_id)
async def admin_receive_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Введите корректный числовой ID:")
        return
    target_id = int(message.text)
    user_data = db.get_user(target_id)
    if not user_data:
        await message.answer("⚠️ Пользователь с таким ID не найден в базе.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Назад", callback_data="admin_panel")]]))
        await state.clear()
        return
    
    await state.update_data(target_id=target_id)
    await show_user_management(message, target_id)
    await state.clear()

@router.callback_query(F.data.startswith("admin:user:"))
async def admin_user_detail_callback(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return
    target_id = int(call.data.split(":")[2])
    await show_user_management(call.message, target_id, is_edit=True)
    await call.answer()

async def show_user_management(message: Message, target_id: int, is_edit: bool = False):
    user_data = db.get_user(target_id)
    if not user_data:
        return
    uid, username, extra, prem, banned = user_data
    uname = f"@{username}" if username else f"ID: {uid}"
    now = int(datetime.now(timezone.utc).timestamp())
    is_prem = prem > now
    status = "🔴 Заблокирован" if banned else ("👑 Админ" if is_admin(uid) else ("⭐ Premium" if is_prem else "👤 Обычный"))
    
    text = (
        f"👤 <b>Управление пользователем:</b> {uname}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"💎 Статус: <b>{status}</b>\n"
        f"📦 Доп. запросов на балансе: <b>{extra}</b>"
    )
    keyboard = [
        [InlineKeyboardButton(text="➕ Выдать запросы", callback_data=f"adm_act:add_req:{uid}"),
         InlineKeyboardButton(text="➖ Забрать запросы", callback_data=f"adm_act:sub_req:{uid}")],
        [InlineKeyboardButton(text="⭐ Выдать Premium (дни)", callback_data=f"adm_act:add_prem:{uid}"),
         InlineKeyboardButton(text="❌ Забрать Premium", callback_data=f"adm_act:rev_prem:{uid}")],
        [InlineKeyboardButton(text="🔨 Бан / 🔓 Разбан", callback_data=f"adm_act:ban:{uid}")],
        [InlineKeyboardButton(text="« К админ-панели", callback_data="admin_panel")],
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    if is_edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")

# Управление действиями с запросами / премиумом (FSM для ввода чисел)
@router.callback_query(F.data.startswith("adm_act:"))
async def admin_actions_dispatcher(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id):
        return
    parts = call.data.split(":")
    action, target_id = parts[1], int(parts[2])
    
    if action == "ban":
        new_ban = db.toggle_ban(target_id)
        status_text = "заблокирован 🔴" if new_ban else "разблокирован 🟢"
        await call.answer(f"Пользователь {status_text}!", show_alert=True)
        await show_user_management(call.message, target_id, is_edit=True)
        return
    
    if action == "rev_prem":
        db.revoke_premium(target_id)
        try:
            await bot.send_message(target_id, "⚠️ Ваша Premium-подписка была аннулирована администратором.")
        except Exception:
            pass
        await call.answer("✅ Премиум успешно забран!", show_alert=True)
        await show_user_management(call.message, target_id, is_edit=True)
        return

    # Для действий требующих ввода числа (запросы или дни према)
    await state.update_data(target_id=target_id, action_type=action)
    if action in ["add_req", "sub_req"]:
        await state.set_state(AdminState.waiting_for_requests_count)
        await call.message.edit_text(
            "✍️ Введите <b>количество запросов</b> числом (например: <code>10</code> или <code>50</code>):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data=f"admin:user:{target_id}")]])
        )
    elif action == "add_prem":
        await state.set_state(AdminState.waiting_for_premium_days)
        await call.message.edit_text(
            "✍️ Введите <b>количество дней Premium</b> числом (например: <code>30</code>):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="« Отмена", callback_data=f"admin:user:{target_id}")]])
        )
    await call.answer()

@router.message(AdminState.waiting_for_requests_count)
async def process_requests_input(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Введите целое число:")
        return
    amount = int(message.text)
    data = await state.get_data()
    target_id = data.get("target_id")
    action_type = data.get("action_type")
    
    if action_type == "add_req":
        db.add_requests(target_id, amount)
        try:
            await bot.send_message(target_id, f"🎉 Вам начислено дополнительных поисков: <b>{amount}</b>!", parse_mode="HTML")
        except Exception:
            pass
        await message.answer(f"✅ Успешно добавлено {amount} запросов пользователю {target_id}!")
    elif action_type == "sub_req":
        db.add_requests(target_id, -amount)
        try:
            await bot.send_message(target_id, f"⚠️ У вас списано поисков: <b>{amount}</b>.", parse_mode="HTML")
        except Exception:
            pass
        await message.answer(f"✅ Успешно списано {amount} запросов у пользователя {target_id}!")
        
    await state.clear()
    await show_user_management(message, target_id)

@router.message(AdminState.waiting_for_premium_days)
async def process_premium_input(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    if not message.text.isdigit():
        await message.answer("⚠️ Введите целое число дней:")
        return
    days = int(message.text)
    data = await state.get_data()
    target_id = data.get("target_id")
    
    db.add_premium(target_id, days)
    try:
        await bot.send_message(target_id, f"⭐ Вам выдана Premium подписка на <b>{days} дней</b>!", parse_mode="HTML")
    except Exception:
        pass
    
    await message.answer(f"✅ Премиум на {days} дней успешно выдан пользователю {target_id}!")
    await state.clear()
    await show_user_management(message, target_id)

# --- РАЗДЕЛ ОПЛАТЫ И ТОВАРОВ (TELEGRAM STARS) ---

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

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    user_id = message.from_user.id
    if payload.startswith("premium:"):
        days = int(payload.split(":")[1])
        db.add_premium(user_id, days)
        await message.answer(f"⭐ Успешно! Premium подписка на {days} дней активирована.")
    elif payload.startswith("pack:"):
        amount = int(payload.split(":")[1])
        db.add_requests(user_id, amount)
        await message.answer(f"📦 Успешно! Вам начислено {amount} поисков.")
    elif payload.startswith("support:"):
        await message.answer("❤️ Огромное спасибо за поддержку проекта!")

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    logging.basicConfig(level=logging.INFO)
    session = AiohttpSession(api=TelegramAPIServer.from_base("http://31.77.9.111:8081"))
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher()
    dp.include_router(router)
    print("Бот запущен с расширенной админ-панелью, анимациями и надежными платежами!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
