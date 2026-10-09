import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- НАСТРОЙКИ ---
TOKEN = "8544958075:AAG6dfQF1_lafEg1Y-yIAMoR_hr1e1pNPAs"
ADMIN_ID = 6203925408

DEFAULT_CARD_NUMBER = "0000 0000 0000 0000"
DEFAULT_CARD_NAME = ""
DEFAULT_SUPPORT = "@imperfreaks"
DEFAULT_PRICE_SELL = 10.0
DEFAULT_PRICE_BUY = 8.0
DEFAULT_GAME_ID = "1000068"
CURRENCY = "₽"

# --- БАЗА ДАННЫХ ---
db = sqlite3.connect("imperator_shop.db")
cursor = db.cursor()

cursor.execute("""CREATE TABLE IF NOT EXISTS stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL,
    price REAL,
    status TEXT DEFAULT 'available'
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    game_id TEXT,
    amount REAL,
    total_price REAL,
    status TEXT,
    photo_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)""")

cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)""")
db.commit()

# --- НАСТРОЙКИ ---
def get_setting(key, default=None):
    cursor.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    return row[0] if row else default

def set_setting(key, value):
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    db.commit()

if get_setting("card_number") is None: set_setting("card_number", DEFAULT_CARD_NUMBER)
if get_setting("card_name") is None: set_setting("card_name", DEFAULT_CARD_NAME)
if get_setting("support") is None: set_setting("support", DEFAULT_SUPPORT)
if get_setting("price_sell") is None: set_setting("price_sell", DEFAULT_PRICE_SELL)
if get_setting("price_buy") is None: set_setting("price_buy", DEFAULT_PRICE_BUY)
if get_setting("game_id") is None: set_setting("game_id", DEFAULT_GAME_ID)

# --- СОСТОЯНИЯ ---
class BuyState(StatesGroup):
    waiting_for_game_id = State()
    waiting_for_amount = State()
    waiting_for_receipt = State()

class SellState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_payout_method = State()
    waiting_for_payout_details = State()
    waiting_for_confirmation = State()

class AdminState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_price = State()
    waiting_for_card_number = State()
    waiting_for_card_name = State()
    waiting_for_support = State()
    waiting_for_price_sell = State()
    waiting_for_price_buy = State()
    waiting_for_broadcast = State()
    waiting_for_user_search = State()
    waiting_for_game_id = State()

# --- ИНИЦИАЛИЗАЦИЯ ---
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- БД ---
def get_stock_total():
    cursor.execute("SELECT SUM(amount) FROM stock WHERE status='available'")
    res = cursor.fetchone()[0]
    return res if res else 0.0

def add_stock(amount, price):
    cursor.execute("INSERT INTO stock (amount, price) VALUES (?, ?)", (amount, price))
    db.commit()

def save_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    if username:
        cursor.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
    db.commit()

# --- ХЕЛПЕР ЧИСТОГО ОТВЕТА ---
async def clean_reply(message: types.Message, text: str, kb=None, state: FSMContext = None, parse_mode="HTML"):
    try:
        await message.delete()
    except Exception:
        pass

    if state:
        data = await state.get_data()
        last_id = data.get("last_bot_msg")
        if last_id:
            try:
                await bot.delete_message(chat_id=message.chat.id, message_id=last_id)
            except Exception:
                pass

    sent = await message.answer(text, reply_markup=kb, parse_mode=parse_mode)
    if state:
        await state.update_data(last_bot_msg=sent.message_id)
    return sent

# --- КЛАВИАТУРЫ ---
def main_menu_kb(user_id: int = 0):
    kb = [
        [InlineKeyboardButton(text="🛒 Купить коины", callback_data="menu_buy"),
         InlineKeyboardButton(text="💸 Продать коины", callback_data="menu_sell")],
        [InlineKeyboardButton(text="📊 Информация", callback_data="menu_info"),
         InlineKeyboardButton(text="👤 Поддержка", callback_data="menu_support")],
    ]
    if user_id == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="👨‍💻 Админ-панель", callback_data="menu_admin")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_menu_kb():
    kb = [
        [InlineKeyboardButton(text="📥 Пополнить склад", callback_data="adm_add"),
         InlineKeyboardButton(text="📦 Остатки склада", callback_data="adm_stock")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"),
         InlineKeyboardButton(text="📜 История заказов", callback_data="adm_history")],
        [InlineKeyboardButton(text="🔍 Поиск по юзеру", callback_data="adm_search"),
         InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="💳 Реквизиты карты", callback_data="adm_card"),
         InlineKeyboardButton(text="💱 Изменить курсы", callback_data="adm_prices")],
        [InlineKeyboardButton(text="🎮 Игровой ID магазина", callback_data="adm_gameid"),
         InlineKeyboardButton(text="👨‍💻 Изменить поддержку", callback_data="adm_support")],
        [InlineKeyboardButton(text="⬅️ Вернуться в магазин", callback_data="menu_home")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главная", callback_data="menu_home")]
    ])

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_home")]
    ])

def admin_back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")]
    ])

# --- ТЕКСТ ГЛАВНОГО МЕНЮ ---
def build_main_text():
    stock = get_stock_total()
    if stock > 10_000_000:
        si, sn = "🟢", "Отличный запас"
    elif stock > 1_000_000:
        si, sn = "🟡", "В наличии"
    elif stock > 0:
        si, sn = "🟠", "Мало, спешите"
    else:
        si, sn = "🔴", "Склад пуст"

    price_sell = float(get_setting("price_sell", DEFAULT_PRICE_SELL))
    price_buy = float(get_setting("price_buy", DEFAULT_PRICE_BUY))

    return (
        f"<b>🏛  I M P E R A T O R   S H O P 🏛</b>\n"
        f"<i>Премиальный обмен игровой валюты</i>\n"
        f"\n"
        f"─────  <b>СТАТУС</b>  ─────\n"
        f"  🟢 Операторы <b>онлайн</b>\n"
        f"  ⭐ Рейтинг <b>5.0</b>\n"
        f"  ⚡ Среднее время выдачи: <b>~10 мин</b>\n"
        f"\n"
        f"─────  <b>СКЛАД</b>  ─────\n"
        f"  {si} В наличии: <b>{stock:,.0f} N</b>\n"
        f"  <i>{sn}</i>\n"
        f"\n"
        f"─────  <b>ТАРИФЫ</b>  ─────\n"
        f"  🔴 <b>Продажа</b>  -  {price_sell} {CURRENCY} / 1кк\n"
        f"  🟢 <b>Скупка</b>   -  {price_buy} {CURRENCY} / 1кк\n"
        f"\n"
        f"<i>Выберите действие ниже ↓</i>"
    )

# =========================================================
# --- ГЛАВНОЕ МЕНЮ ---
# =========================================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    save_user(message.from_user.id, message.from_user.username)
    try: await message.delete()
    except: pass
    await message.answer(
        build_main_text(),
        reply_markup=main_menu_kb(message.from_user.id),
        parse_mode="HTML"
    )

@dp.message(Command("home"))
async def cmd_home(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_start(message)

@dp.callback_query(F.data == "menu_home")
async def menu_home(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    save_user(callback.from_user.id, callback.from_user.username)
    try:
        await callback.message.edit_text(
            build_main_text(),
            reply_markup=main_menu_kb(callback.from_user.id),
            parse_mode="HTML"
        )
    except Exception:
        await callback.message.answer(
            build_main_text(),
            reply_markup=main_menu_kb(callback.from_user.id),
            parse_mode="HTML"
        )
    await callback.answer()

@dp.callback_query(F.data == "menu_info")
async def menu_info(callback: types.CallbackQuery, state: FSMContext):
    price_sell = get_setting("price_sell", DEFAULT_PRICE_SELL)
    price_buy = get_setting("price_buy", DEFAULT_PRICE_BUY)
    support_contact = get_setting("support", DEFAULT_SUPPORT)

    text = (
        f"<b>📋  Информация об Imperator Shop</b>\n"
        f"<i>Всё, что нужно знать перед сделкой</i>\n"
        f"\n"
        f"─────  <b>ПРАВИЛА</b>  ─────\n"
        f"  🛡 Только чистые сделки\n"
        f"  ⚡ Моментальные выплаты\n"
        f"  🔒 Работаем 24/7\n"
        f"\n"
        f"─────  <b>КУРСЫ</b>  ─────\n"
        f"  💵 Покупка у нас  -  <b>{price_sell} {CURRENCY}</b> / 1кк\n"
        f"  💰 Скупка у вас   -  <b>{price_buy} {CURRENCY}</b> / 1кк\n"
        f"\n"
        f"─────  <b>КОНТАКТ</b>  ─────\n"
        f"  👨‍💻 Поддержка: {support_contact}\n"
        f"\n"
        f"<i>Спасибо, что выбираете нас 🏛</i>"
    )
    await callback.message.edit_text(text, reply_markup=back_kb(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "menu_support")
async def menu_support(callback: types.CallbackQuery, state: FSMContext):
    support_contact = get_setting("support", DEFAULT_SUPPORT)
    await callback.message.edit_text(
        f"👨‍💻 <b>Поддержка Imperator Shop</b>\n\n"
        f"По всем вопросам пишите: {support_contact}",
        reply_markup=back_kb(), parse_mode="HTML"
    )
    await callback.answer()

# =========================================================
# --- ПОКУПКА ---
# =========================================================

@dp.callback_query(F.data == "menu_buy")
async def menu_buy(callback: types.CallbackQuery, state: FSMContext):
    stock = get_stock_total()
    if stock <= 0:
        await callback.message.edit_text(
            "⚠️ <b>Извините, склад временно пуст!</b>\nОператор уже пополняет запасы. Загляните позже.",
            reply_markup=back_kb(), parse_mode="HTML"
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "🎮 <b>Шаг 1/3: Введите ваш игровой ID (Никнейм)</b>\n\n"
        "<i>Убедитесь, что ID указан верно, переводы на неверный ID не возвращаются.</i>",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await state.set_state(BuyState.waiting_for_game_id)
    await callback.answer()

@dp.message(BuyState.waiting_for_game_id)
async def buy_amount(message: types.Message, state: FSMContext):
    await state.update_data(game_id=message.text)
    await clean_reply(
        message,
        "💎 <b>Шаг 2/3: Введите сумму покупки в N</b>\n\n"
        "<i>Пример: 1000000 (один миллион)</i>",
        kb=cancel_kb(),
        state=state
    )
    await state.set_state(BuyState.waiting_for_amount)

@dp.message(BuyState.waiting_for_amount)
async def buy_invoice(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", "").replace(",", ""))
    except ValueError:
        await clean_reply(message, "❌ Введите корректное число.", kb=cancel_kb(), state=state)
        return

    stock = get_stock_total()
    if amount > stock:
        await clean_reply(
            message,
            f"❌ <b>Недостаточно товара!</b>\nНа складе максимум: <code>{stock:,.0f} N</code>",
            kb=cancel_kb(),
            state=state
        )
        return

    price_sell = float(get_setting("price_sell", DEFAULT_PRICE_SELL))
    total_price = (amount / 1_000_000) * price_sell
    data = await state.get_data()
    game_id = data['game_id']
    card_number = get_setting("card_number", DEFAULT_CARD_NUMBER)
    card_name = get_setting("card_name", DEFAULT_CARD_NAME)

    cursor.execute("INSERT INTO orders (user_id, game_id, amount, total_price, status) VALUES (?, ?, ?, ?, ?)",
                   (message.from_user.id, game_id, amount, total_price, "pending_payment"))
    db.commit()
    order_id = cursor.lastrowid

    await clean_reply(
        message,
        f"🧾 <b>Шаг 3/3: Оплата заказа #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🎮 Ваш ID: <code>{game_id}</code>\n"
        f"💎 Количество: <b>{amount:,.0f} N</b>\n"
        f"💵 К оплате: <b>{total_price:.2f} {CURRENCY}</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"💳 <b>Реквизиты для перевода:</b>\n"
        f"┣ Карта: <code>{card_number}</code>\n"
        f"┗ Получатель: <b>{card_name}</b>\n\n"
        f"📸 <b>После оплаты отправьте скриншот чека прямо в этот чат.</b>",
        kb=cancel_kb(),
        state=state
    )
    await state.set_state(BuyState.waiting_for_receipt)

@dp.message(BuyState.waiting_for_receipt, F.photo)
async def handle_receipt(message: types.Message, state: FSMContext):
    cursor.execute("SELECT id, amount, total_price, game_id FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1", (message.from_user.id,))
    order = cursor.fetchone()

    if not order:
        await message.answer("❌ Ошибка: заказ не найден. Начните заново.")
        await state.clear()
        return

    order_id, amount, price, game_id = order
    photo_id = message.photo[-1].file_id

    cursor.execute("UPDATE orders SET photo_id=?, status='checking' WHERE id=?", (photo_id, order_id))
    db.commit()

    await message.answer(
        "⏳ <b>Чек получен и отправлен на проверку!</b>\n\n"
        "Оператор проверит поступление средств и выдаст коины в течение 5-15 минут.",
        reply_markup=back_kb(), parse_mode="HTML"
    )
    await state.clear()

    admin_text = (
        f"🔔 <b>НОВАЯ ЗАЯВКА НА ПОКУПКУ #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 Покупатель: @{message.from_user.username} (<code>{message.from_user.id}</code>)\n"
        f"🎮 Игровой ID: <code>{game_id}</code>\n"
        f"💎 Сумма: <b>{amount:,.0f} N</b>\n"
        f"💰 К оплате: <b>{price:.2f} {CURRENCY}</b>\n"
        f"━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data=f"confirm_{order_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{order_id}")]
    ])
    await bot.send_photo(ADMIN_ID, photo_id, caption=admin_text, reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data.startswith("confirm_"))
async def confirm_order(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[1]
    cursor.execute("SELECT user_id, amount, game_id FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()

    if not order:
        await callback.answer("Заказ не найден.", show_alert=True)
        return

    user_id, amount, game_id = order
    cursor.execute("UPDATE orders SET status='completed' WHERE id=?", (order_id,))

    remaining = amount
    cursor.execute("SELECT id, amount FROM stock WHERE status='available' AND amount > 0 ORDER BY id ASC")
    for s_id, s_amount in cursor.fetchall():
        if remaining <= 0: break
        if s_amount >= remaining:
            cursor.execute("UPDATE stock SET amount=? WHERE id=?", (s_amount - remaining, s_id))
            remaining = 0
        else:
            cursor.execute("UPDATE stock SET amount=0, status='sold' WHERE id=?", (s_id,))
            remaining -= s_amount
    db.commit()

    await bot.send_message(
        user_id,
        f"🎉 <b>Заказ #{order_id} успешно выполнен!</b>\n\n"
        f"💎 <code>{amount:,.0f} N</code> зачислены на ваш игровой ID: <code>{game_id}</code>\n"
        f"Спасибо за покупку в Imperator Shop!",
        parse_mode="HTML"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ <b>СТАТУС: ВЫПОЛНЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Заказ выдан!")

@dp.callback_query(F.data.startswith("reject_"))
async def reject_order(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[1]
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()
    if not row:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    user_id = row[0]
    cursor.execute("UPDATE orders SET status='rejected' WHERE id=?", (order_id,))
    db.commit()

    await bot.send_message(
        user_id,
        f"❌ <b>Заказ #{order_id} отклонен.</b>\n\n"
        f"Средства не поступили или чек недействителен. Свяжитесь с поддержкой.",
        parse_mode="HTML"
    )
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n❌ <b>СТАТУС: ОТКЛОНЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Заказ отклонен.")

# =========================================================
# --- ПРОДАЖА ---
# =========================================================

@dp.callback_query(F.data == "menu_sell")
async def menu_sell(callback: types.CallbackQuery, state: FSMContext):
    price_buy = get_setting("price_buy", DEFAULT_PRICE_BUY)
    shop_game_id = get_setting("game_id", DEFAULT_GAME_ID)

    await callback.message.edit_text(
        f"💸 <b>Продажа коинов в Imperator Shop</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"  💱 Курс скупки: <b>{price_buy} {CURRENCY}</b> / 1кк\n"
        f"  🎮 Наш игровой ID: <code>{shop_game_id}</code>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"<b>Шаг 1/3: Введите количество N, которое хотите продать</b>\n\n"
        f"<i>Минимум: 1 000 000 N</i>",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await state.set_state(SellState.waiting_for_amount)
    await callback.answer()

@dp.message(SellState.waiting_for_amount)
async def sell_show_instructions(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", "").replace(",", ""))
    except ValueError:
        await clean_reply(message, "❌ Введите корректное число.", kb=cancel_kb(), state=state)
        return

    if amount < 1_000_000:
        await clean_reply(
            message,
            "❌ Минимальная сумма продажи - <b>1 000 000 N</b>.",
            kb=cancel_kb(),
            state=state
        )
        return

    price_buy = float(get_setting("price_buy", DEFAULT_PRICE_BUY))
    total_price = (amount / 1_000_000) * price_buy
    shop_game_id = get_setting("game_id", DEFAULT_GAME_ID)
    await state.update_data(amount=amount, total_price=total_price)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 На карту", callback_data="payout_card")],
        [InlineKeyboardButton(text="📱 На телефон (СБП)", callback_data="payout_phone")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_home")]
    ])
    await clean_reply(
        message,
        f"📋 <b>Шаг 2/3: Переведите коины нам</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"  🎮 Игровой ID магазина: <code>{shop_game_id}</code>\n"
        f"  💎 Сумма перевода: <b>{amount:,.0f} N</b>\n"
        f"  💰 Вы получите: <b>{total_price:.2f} {CURRENCY}</b>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"⚠️ Зайдите в игру и переведите указанную сумму на наш ID.\n\n"
        f"<b>Шаг 3/3: Куда перевести вам деньги?</b>",
        kb=kb,
        state=state
    )
    await state.set_state(SellState.waiting_for_payout_method)

@dp.callback_query(F.data == "payout_card", SellState.waiting_for_payout_method)
async def payout_card_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💳 <b>Введите номер вашей карты</b>\n\n<i>Например: 2200 0000 0000 0000</i>",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await state.set_state(SellState.waiting_for_payout_details)
    await callback.answer()

@dp.callback_query(F.data == "payout_phone", SellState.waiting_for_payout_method)
async def payout_phone_choice(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📱 <b>Введите номер телефона (СБП)</b>\n\n<i>Например: +7 999 123-45-67</i>",
        reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await state.set_state(SellState.waiting_for_payout_details)
    await callback.answer()

@dp.message(SellState.waiting_for_payout_details)
async def payout_details_received(message: types.Message, state: FSMContext):
    payout_details = message.text.strip()
    data = await state.get_data()
    amount = data['amount']
    total_price = data['total_price']
    shop_game_id = get_setting("game_id", DEFAULT_GAME_ID)
    await state.update_data(payout_details=payout_details)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я перевёл коины", callback_data="sell_i_paid")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="menu_home")]
    ])
    await clean_reply(
        message,
        f"📋 <b>Проверьте данные перед отправкой:</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"  🎮 Куда перевести: <code>{shop_game_id}</code>\n"
        f"  💎 Сумма: <b>{amount:,.0f} N</b>\n"
        f"  💰 К получению: <b>{total_price:.2f} {CURRENCY}</b>\n"
        f"  💳 Реквизит для выплаты: <code>{payout_details}</code>\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"Переведите коины на указанный ID и нажмите кнопку ниже.",
        kb=kb,
        state=state
    )
    await state.set_state(SellState.waiting_for_confirmation)

@dp.callback_query(F.data == "sell_i_paid", SellState.waiting_for_confirmation)
async def sell_user_confirmed(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    total_price = data['total_price']
    payout_details = data['payout_details']

    cursor.execute(
        "INSERT INTO orders (user_id, game_id, amount, total_price, status, photo_id) VALUES (?, ?, ?, ?, ?, ?)",
        (callback.from_user.id, "-", -amount, -total_price, "sell_waiting_admin", payout_details)
    )
    db.commit()
    order_id = cursor.lastrowid

    await callback.message.edit_text(
        f"⏳ <b>Заявка #{order_id} отправлена оператору!</b>\n\n"
        f"Мы проверим поступление коинов и переведём деньги на указанные реквизиты. "
        f"Обычно это занимает до 5 минут.",
        reply_markup=back_kb(), parse_mode="HTML"
    )
    await state.clear()

    admin_text = (
        f"💸 <b>НОВАЯ ЗАЯВКА НА ПРОДАЖУ #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 Продавец: @{callback.from_user.username} (<code>{callback.from_user.id}</code>)\n"
        f"💎 Продаёт: <b>{amount:,.0f} N</b>\n"
        f"💰 К выплате: <b>{total_price:.2f} {CURRENCY}</b>\n"
        f"💳 Реквизит: <code>{payout_details}</code>\n"
        f"━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Коины получены", callback_data=f"sell_confirm_{order_id}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"sell_reject_{order_id}")]
    ])
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("sell_confirm_"))
async def sell_confirm(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[2]
    cursor.execute("SELECT user_id, amount, total_price, photo_id FROM orders WHERE id=?", (order_id,))
    order = cursor.fetchone()

    if not order:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    user_id, amount, total_price, payout_details = order
    cursor.execute("UPDATE orders SET status='sell_awaiting_payout' WHERE id=?", (order_id,))
    cursor.execute("INSERT INTO stock (amount, price, status) VALUES (?, ?, 'available')",
                   (abs(amount), float(get_setting("price_buy", DEFAULT_PRICE_BUY))))
    db.commit()

    await bot.send_message(
        user_id,
        f"✅ <b>Коины получены! Заявка #{order_id}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"💰 Сумма к выплате: <b>{total_price:.2f} {CURRENCY}</b>\n"
        f"💳 Реквизит: <code>{payout_details}</code>\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Оператор переведёт деньги в течение 5-15 минут.</i>",
        parse_mode="HTML"
    )

    new_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 Деньги отправлены", callback_data=f"sell_paid_{order_id}")]
    ])
    await callback.message.edit_text(
        callback.message.html_text + "\n\n✅ <b>Коины подтверждены. Ожидаем выплату.</b>",
        reply_markup=new_kb, parse_mode="HTML"
    )
    await callback.answer("Коины подтверждены!")

@dp.callback_query(F.data.startswith("sell_paid_"))
async def sell_paid(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[2]
    cursor.execute("SELECT user_id, total_price FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    user_id, total_price = row
    total_price = abs(total_price)
    cursor.execute("UPDATE orders SET status='sell_completed' WHERE id=?", (order_id,))
    db.commit()

    await bot.send_message(
        user_id,
        f"🎉 <b>Заявка #{order_id} полностью завершена!</b>\n\n"
        f"💸 <code>{total_price:.2f} {CURRENCY}</code> отправлены на ваши реквизиты.\n"
        f"Спасибо за сделку! 🏛",
        parse_mode="HTML"
    )
    await callback.message.edit_text(
        callback.message.html_text + "\n\n💸 <b>СТАТУС: ВЫПЛАЧЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Заявка закрыта!")

@dp.callback_query(F.data.startswith("sell_reject_"))
async def sell_reject(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[2]
    cursor.execute("SELECT user_id FROM orders WHERE id=?", (order_id,))
    row = cursor.fetchone()

    if not row:
        await callback.answer("Заявка не найдена.", show_alert=True)
        return

    user_id = row[0]
    cursor.execute("UPDATE orders SET status='sell_rejected' WHERE id=?", (order_id,))
    db.commit()

    await bot.send_message(
        user_id,
        f"❌ <b>Заявка на продажу #{order_id} отклонена.</b>\n\n"
        f"Коины не поступили, либо сделка отменена. Свяжитесь с поддержкой.",
        parse_mode="HTML"
    )
    await callback.message.edit_text(
        callback.message.html_text + "\n\n❌ <b>СТАТУС: ОТКЛОНЕНО</b>",
        parse_mode="HTML"
    )
    await callback.answer("Заявка отклонена.")

# =========================================================
# --- АДМИН ПАНЕЛЬ ---
# =========================================================

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try: await message.delete()
    except: pass
    await message.answer(
        "👨‍💻 <b>Панель управления Imperator Shop</b>\nВыберите действие:",
        reply_markup=admin_menu_kb(), parse_mode="HTML"
    )

@dp.callback_query(F.data == "menu_admin")
async def menu_admin(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text(
        "👨‍💻 <b>Панель управления Imperator Shop</b>\nВыберите действие:",
        reply_markup=admin_menu_kb(), parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "adm_back")
async def adm_back(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "👨‍💻 <b>Панель управления Imperator Shop</b>\nВыберите действие:",
        reply_markup=admin_menu_kb(), parse_mode="HTML"
    )
    await callback.answer()

# --- СКЛАД ---

@dp.callback_query(F.data == "adm_add")
async def adm_add(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    await callback.message.edit_text(
        "📦 Введите количество N для добавления на склад:\n<i>(Пример: 50000000)</i>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_amount)
    await callback.answer()

@dp.message(AdminState.waiting_for_amount)
async def adm_add_amount(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(" ", ""))
        await state.update_data(amount=amount)
        await clean_reply(
            message,
            "💵 Введите себестоимость (цену за 1кк, например 8.0):",
            kb=admin_back_kb(),
            state=state
        )
        await state.set_state(AdminState.waiting_for_price)
    except:
        await clean_reply(message, "❌ Введите корректное число.", kb=admin_back_kb(), state=state)

@dp.message(AdminState.waiting_for_price)
async def adm_add_price(message: types.Message, state: FSMContext):
    try:
        price = float(message.text)
        data = await state.get_data()
        add_stock(data['amount'], price)
        await clean_reply(
            message,
            f"✅ <b>Успешно!</b>\nНа склад добавлено <code>{data['amount']:,.0f} N</code>.",
            kb=admin_menu_kb(),
            state=state
        )
        await state.clear()
    except:
        await clean_reply(message, "❌ Введите корректное число.", kb=admin_back_kb(), state=state)

@dp.callback_query(F.data == "adm_stock")
async def adm_stock(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    cursor.execute("SELECT amount, price FROM stock WHERE status='available'")
    items = cursor.fetchall()
    total = sum(i[0] for i in items)
    text = f"📊 <b>Имперские запасы (Склад):</b>\n━━━━━━━━━━━━━━\n"
    text += f"🔹 <b>Всего доступно:</b> <code>{total:,.0f} N</code>\n\n"
    n = 0
    for amt, pr in items:
        if amt > 0:
            n += 1
            text += f"📦 Партия {n}: <code>{amt:,.0f} N</code> <i>(закуп {pr}₽)</i>\n"
    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="HTML")
    await callback.answer()

# --- СТАТИСТИКА ---

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return

    cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='completed'")
    c_count, c_sum = cursor.fetchone()
    c_count = c_count or 0
    c_sum = c_sum or 0

    cursor.execute("SELECT COUNT(*), SUM(total_price) FROM orders WHERE status='sell_completed'")
    s_count, s_sum = cursor.fetchone()
    s_count = s_count or 0
    s_sum = abs(s_sum or 0)

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('checking','sell_waiting_admin','sell_awaiting_payout')")
    pend = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status IN ('rejected','sell_rejected')")
    rej = cursor.fetchone()[0] or 0

    cursor.execute("SELECT SUM(amount) FROM stock WHERE status='available'")
    left = cursor.fetchone()[0] or 0

    cursor.execute("SELECT COUNT(*) FROM users")
    users = cursor.fetchone()[0] or 0

    profit = c_sum - s_sum
    profit_emoji = "📈" if profit >= 0 else "📉"

    text = (
        f"📊 <b>Статистика Imperator Shop</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"📦 Товара на складе: <b>{left:,.0f} N</b>\n"
        f"\n"
        f"─────  <b>ЗАКАЗЫ</b>  ─────\n"
        f"  ✅ Продано нами: <b>{c_count}</b>\n"
        f"  💸 Куплено нами: <b>{s_count}</b>\n"
        f"  ⏳ На проверке: <b>{pend}</b>\n"
        f"  ❌ Отклонено: <b>{rej}</b>\n"
        f"\n"
        f"─────  <b>ДОХОД</b>  ─────\n"
        f"  💰 Продажа коинов: <b>+{c_sum:.2f} {CURRENCY}</b>\n"
        f"\n"
        f"─────  <b>РАСХОД</b>  ─────\n"
        f"  💸 Скупка у игроков: <b>-{s_sum:.2f} {CURRENCY}</b>\n"
        f"\n"
        f"━━━━━━━━━━━━━━\n"
        f"{profit_emoji} <b>Чистая прибыль:</b> <b>{profit:+.2f} {CURRENCY}</b>\n"
    )
    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="HTML")
    await callback.answer()

# --- ИСТОРИЯ ---

@dp.callback_query(F.data == "adm_history")
async def adm_history(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return

    cursor.execute("SELECT id, user_id, amount, total_price, status FROM orders ORDER BY id DESC LIMIT 10")
    orders = cursor.fetchall()

    if not orders:
        await callback.answer("Заказов пока нет.", show_alert=True); return

    emo = {"pending_payment":"🕐","checking":"⏳","completed":"✅","rejected":"❌",
           "sell_waiting_admin":"💸","sell_awaiting_payout":"💳","sell_completed":"🎉","sell_rejected":"🚫"}
    text = "📜 <b>Последние 10 заказов:</b>\n━━━━━━━━━━━━━━\n"
    for o_id, u_id, amt, pr, st in orders:
        text += f"{emo.get(st,'❔')} <b>#{o_id}</b> · <code>{amt:,.0f} N</code> · <b>{abs(pr):.2f}₽</b> · <code>{u_id}</code>\n"

    await callback.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode="HTML")
    await callback.answer()

# --- ПОИСК ---

@dp.callback_query(F.data == "adm_search")
async def adm_search(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    await callback.message.edit_text(
        "🔍 <b>Введите данные для поиска:</b>\n\n"
        "• Telegram ID - например <code>6203925408</code>\n"
        "• или @username - например <code>@haslich</code>",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_user_search)
    await callback.answer()

@dp.message(AdminState.waiting_for_user_search)
async def adm_search_result(message: types.Message, state: FSMContext):
    query = message.text.strip()
    user_id = None
    username_found = None

    if query.startswith("@"):
        cursor.execute("SELECT user_id, username FROM users WHERE LOWER(username)=?", (query[1:].lower(),))
        row = cursor.fetchone()
        if row: user_id, username_found = row
    else:
        try:
            user_id = int(query)
            cursor.execute("SELECT username FROM users WHERE user_id=?", (user_id,))
            row = cursor.fetchone()
            username_found = row[0] if row else None
        except ValueError:
            cursor.execute("SELECT user_id, username FROM users WHERE LOWER(username)=?", (query.lower(),))
            row = cursor.fetchone()
            if row: user_id, username_found = row

    if not user_id:
        await clean_reply(
            message,
            f"❌ Пользователь <code>{query}</code> не найден.",
            kb=admin_back_kb(),
            state=state
        )
        await state.clear()
        return

    cursor.execute("SELECT id, amount, total_price, status FROM orders WHERE user_id=? ORDER BY id DESC", (user_id,))
    orders = cursor.fetchall()
    emo = {"pending_payment":"🕐","checking":"⏳","completed":"✅","rejected":"❌",
           "sell_waiting_admin":"💸","sell_awaiting_payout":"💳","sell_completed":"🎉","sell_rejected":"🚫"}
    uname = f"@{username_found}" if username_found else "-"

    text = (
        f"👤 <b>Профиль пользователя</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"  🆔 ID: <code>{user_id}</code>\n"
        f"  📛 Юзернейм: {uname}\n"
        f"  📦 Всего заказов: <b>{len(orders)}</b>\n\n"
    )
    for o_id, amt, pr, st in orders[:5]:
        text += f"  {emo.get(st,'❔')} #{o_id} · <code>{amt:,.0f} N</code> · <b>{abs(pr):.2f}₽</b>\n"

    await clean_reply(message, text, kb=admin_back_kb(), state=state)
    await state.clear()

# --- РАССЫЛКА ---

@dp.callback_query(F.data == "adm_broadcast")
async def adm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    await callback.message.edit_text(
        f"📢 <b>Рассылка</b>\n\n"
        f"Сообщение получат <b>{count}</b> пользователей.\n\n"
        f"Отправьте текст (можно с HTML-разметкой).",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.answer()

@dp.message(AdminState.waiting_for_broadcast)
async def adm_broadcast_send(message: types.Message, state: FSMContext):
    text = message.html_text
    try: await message.delete()
    except: pass

    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    sent = 0; failed = 0
    status_msg = await message.answer(f"⏳ Отправляю {len(users)} сообщений...")
    for (uid,) in users:
        try:
            await bot.send_message(uid, text, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.05)
        except: failed += 1
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n\n"
        f"  📤 Отправлено: <b>{sent}</b>\n"
        f"  ❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML"
    )
    await state.clear()
    await message.answer("Готово.", reply_markup=admin_menu_kb())

# --- КАРТА ---

@dp.callback_query(F.data == "adm_card")
async def adm_card(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    card = get_setting("card_number"); name = get_setting("card_name")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить номер", callback_data="edit_card_number")],
        [InlineKeyboardButton(text="✏️ Изменить получателя", callback_data="edit_card_name")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")]
    ])
    await callback.message.edit_text(
        f"💳 <b>Текущие реквизиты:</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"  💳 Карта: <code>{card}</code>\n"
        f"  👤 Получатель: <b>{name}</b>",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "edit_card_number")
async def edit_card_number(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("💳 Введите новый номер карты:", reply_markup=admin_back_kb())
    await state.set_state(AdminState.waiting_for_card_number)
    await callback.answer()

@dp.callback_query(F.data == "edit_card_name")
async def edit_card_name(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("👤 Введите новое имя получателя:", reply_markup=admin_back_kb())
    await state.set_state(AdminState.waiting_for_card_name)
    await callback.answer()

@dp.message(AdminState.waiting_for_card_number)
async def save_card_number(message: types.Message, state: FSMContext):
    set_setting("card_number", message.text.strip())
    await clean_reply(message, f"✅ Карта обновлена: <code>{message.text}</code>",
                      kb=admin_menu_kb(), state=state)
    await state.clear()

@dp.message(AdminState.waiting_for_card_name)
async def save_card_name(message: types.Message, state: FSMContext):
    set_setting("card_name", message.text.strip())
    await clean_reply(message, f"✅ Получатель обновлён: <b>{message.text}</b>",
                      kb=admin_menu_kb(), state=state)
    await state.clear()

# --- КУРСЫ ---

@dp.callback_query(F.data == "adm_prices")
async def adm_prices(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    sell = get_setting("price_sell"); buy = get_setting("price_buy")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Курс продажи", callback_data="edit_price_sell")],
        [InlineKeyboardButton(text="✏️ Курс скупки", callback_data="edit_price_buy")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")]
    ])
    await callback.message.edit_text(
        f"💱 <b>Текущие курсы:</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"  🔴 Продажа: <b>{sell} {CURRENCY}</b> / 1кк\n"
        f"  🟢 Скупка:  <b>{buy} {CURRENCY}</b> / 1кк",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "edit_price_sell")
async def edit_price_sell(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🔴 Введите новый курс ПРОДАЖИ (за 1кк):", reply_markup=admin_back_kb())
    await state.set_state(AdminState.waiting_for_price_sell)
    await callback.answer()

@dp.callback_query(F.data == "edit_price_buy")
async def edit_price_buy(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("🟢 Введите новый курс СКУПКИ (за 1кк):", reply_markup=admin_back_kb())
    await state.set_state(AdminState.waiting_for_price_buy)
    await callback.answer()

@dp.message(AdminState.waiting_for_price_sell)
async def save_price_sell(message: types.Message, state: FSMContext):
    try:
        val = float(message.text)
        set_setting("price_sell", val)
        await clean_reply(message, f"✅ Курс продажи: <b>{val} {CURRENCY}</b>",
                          kb=admin_menu_kb(), state=state)
        await state.clear()
    except:
        await clean_reply(message, "❌ Введите число, например 10.0", kb=admin_back_kb(), state=state)

@dp.message(AdminState.waiting_for_price_buy)
async def save_price_buy(message: types.Message, state: FSMContext):
    try:
        val = float(message.text)
        set_setting("price_buy", val)
        await clean_reply(message, f"✅ Курс скупки: <b>{val} {CURRENCY}</b>",
                          kb=admin_menu_kb(), state=state)
        await state.clear()
    except:
        await clean_reply(message, "❌ Введите число, например 8.0", kb=admin_back_kb(), state=state)

# --- ПОДДЕРЖКА ---

@dp.callback_query(F.data == "adm_support")
async def adm_support(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    sup = get_setting("support")
    await callback.message.edit_text(
        f"👨‍💻 <b>Текущий контакт поддержки:</b> {sup}\n\n"
        f"Введите новый (например: @new_support):",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_support)
    await callback.answer()

@dp.message(AdminState.waiting_for_support)
async def save_support(message: types.Message, state: FSMContext):
    set_setting("support", message.text.strip())
    await clean_reply(message, f"✅ Поддержка обновлена: <b>{message.text}</b>",
                      kb=admin_menu_kb(), state=state)
    await state.clear()

# --- ИГРОВОЙ ID ---

@dp.callback_query(F.data == "adm_gameid")
async def adm_gameid(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа.", show_alert=True); return
    gid = get_setting("game_id", DEFAULT_GAME_ID)
    await callback.message.edit_text(
        f"🎮 <b>Текущий игровой ID магазина:</b> <code>{gid}</code>\n\n"
        f"Введите новый:",
        reply_markup=admin_back_kb(), parse_mode="HTML"
    )
    await state.set_state(AdminState.waiting_for_game_id)
    await callback.answer()

@dp.message(AdminState.waiting_for_game_id)
async def save_game_id(message: types.Message, state: FSMContext):
    set_setting("game_id", message.text.strip())
    await clean_reply(message, f"✅ Игровой ID обновлён: <code>{message.text}</code>",
                      kb=admin_menu_kb(), state=state)
    await state.clear()

# =========================================================
# --- ЗАПУСК ---
# =========================================================

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Imperator Shop запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())