import asyncio
import random
import string
import aiosqlite
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

TOKEN = "8387271416:AAEdOB6BZv1AJDVU88-R9oL3E8OVCdbo4hY"
bot = Bot(token=TOKEN)
dp = Dispatcher()

DB_FILE = "casino.db"
codes_db = "codes.db"

# --- Главное меню ---
def main_menu(balance):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(f"Баланс: {balance}💎")],
            [KeyboardButton("Вывод 💎"), KeyboardButton("Пополнить 💸")],
            [KeyboardButton("Игра 💰")]
        ],
        resize_keyboard=True
    )

withdraw_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("Вывод"), KeyboardButton("Отмена")]],
    resize_keyboard=True
)
topup_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("Пополнить"), KeyboardButton("Отмена")]],
    resize_keyboard=True
)
game_action_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("Далее"), KeyboardButton("Отмена")]],
    resize_keyboard=True
)
color_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton("⚫ Черный"), KeyboardButton("⚪ Белый")],
              [KeyboardButton("Отмена")]],
    resize_keyboard=True
)

# --- Инициализация баз ---
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 0
        )
        """)
        await db.commit()
    async with aiosqlite.connect(codes_db) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS codes (
            code TEXT PRIMARY KEY,
            value REAL
        )
        """)
        await db.commit()

# --- Баланс ---
async def get_balance(user_id):
    async with aiosqlite.connect(DB_FILE) as db:
        cursor = await db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return row[0]
        else:
            await db.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
            await db.commit()
            return 0

async def change_balance(user_id, amount):
    current = await get_balance(user_id)
    new_balance = current + amount
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
        await db.commit()
    return new_balance

# --- /start ---
@dp.message(Command("start"))
async def start(msg: types.Message):
    balance = await get_balance(msg.from_user.id)
    await msg.answer("Добро пожаловать в казино! 🎲", reply_markup=main_menu(balance))

# --- Главное меню ---
@dp.message(lambda m: m.text == "Вывод 💎")
async def withdraw(msg: types.Message):
    await msg.answer("Чтобы произвести вывод долларов в звезды нажмите на кнопку ниже.", reply_markup=withdraw_menu)

@dp.message(lambda m: m.text == "Пополнить 💸")
async def topup(msg: types.Message):
    await msg.answer("Чтобы пополнить баланс долларов нажмите на кнопку ниже.", reply_markup=topup_menu)

@dp.message(lambda m: m.text == "Игра 💰")
async def start_game(msg: types.Message):
    await msg.answer("Введите ставку для игры:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Отмена")))

# --- Вывод / Пополнение ---
@dp.message(lambda m: m.text in ["Вывод", "Пополнить"])
async def open_chat(msg: types.Message):
    await msg.answer("Открываем чат с @WWonderFFull", reply_markup=None)

@dp.message(lambda m: m.text == "Отмена")
async def cancel(msg: types.Message):
    balance = await get_balance(msg.from_user.id)
    await msg.answer("Возврат в главное меню.", reply_markup=main_menu(balance))

# --- Игровой процесс ---
user_bets = {}

@dp.message(lambda m: m.text.replace('.', '', 1).isdigit())
async def input_bet(msg: types.Message):
    bet = float(msg.text)
    balance = await get_balance(msg.from_user.id)
    if bet <= 0:
        await msg.answer("Ставка должна быть больше 0.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Отмена")))
        return
    if bet > balance:
        await msg.answer(f"Недостаточно средств! Баланс: {balance}💎", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Отмена")))
        return
    user_bets[msg.from_user.id] = bet
    await msg.answer(f"Ставка: {bet}$", reply_markup=game_action_menu)

@dp.message(lambda m: m.text == "Далее")
async def play_game(msg: types.Message):
    if msg.from_user.id not in user_bets:
        await msg.answer("Сначала введите ставку!", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Отмена")))
        return
    bet = user_bets[msg.from_user.id]
    await change_balance(msg.from_user.id, -bet)
    await msg.answer(f"Ставка {bet}$ принята. Выберите цвет:", reply_markup=color_menu)

@dp.message(lambda m: m.text in ["⚫ Черный", "⚪ Белый"])
async def choose_color(msg: types.Message):
    if msg.from_user.id not in user_bets:
        await msg.answer("Сначала введите ставку!", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Отмена")))
        return
    bet = user_bets[msg.from_user.id]
    choice = "черный" if "Черный" in msg.text else "белый"

    # Анимация в одном сообщении
    anim_msg = await msg.answer("🎲 Крутим...")
    for frame in ["🎲 Крутим.  ", "🎲 Крутим.. ", "🎲 Крутим..."]:
        await asyncio.sleep(0.7)
        await bot.edit_message_text(frame, chat_id=anim_msg.chat.id, message_id=anim_msg.message_id)

    result = random.choice(["черный", "белый"])
    if result == choice:
        win = bet*2
        await change_balance(msg.from_user.id, win)
        await bot.edit_message_text(f"🎉 Выпал {result.upper()}! Вы выиграли {win}💎", chat_id=anim_msg.chat.id, message_id=anim_msg.message_id)
    else:
        await bot.edit_message_text(f"💀 Выпал {result.upper()}! Вы проиграли {bet}💎", chat_id=anim_msg.chat.id, message_id=anim_msg.message_id)

    user_bets.pop(msg.from_user.id)
    balance = await get_balance(msg.from_user.id)
    await msg.answer("Возврат в главное меню.", reply_markup=main_menu(balance))

# --- /code и /promo ---
@dp.message(Command("code"))
async def generate_code(msg: types.Message):
    # Только для тебя
    if msg.from_user.username != "WWonderFFull":
        await msg.answer("❌ У вас нет прав для создания кода!")
        return
    try:
        value = float(msg.text.split()[1])
    except:
        await msg.answer("Используй: /code <сумма>")
        return
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))
    async with aiosqlite.connect(codes_db) as db:
        await db.execute("INSERT INTO codes (code, value) VALUES (?, ?)", (code, value))
        await db.commit()
    await msg.answer(f"Сгенерирован код: {code} на {value}$")

@dp.message(Command("promo"))
async def apply_code(msg: types.Message):
    try:
        user_code = msg.text.split()[1]
    except:
        await msg.answer("Используй: /promo <код>")
        return
    async with aiosqlite.connect(codes_db) as db:
        cursor = await db.execute("SELECT value FROM codes WHERE code = ?", (user_code,))
        row = await cursor.fetchone()
        if row:
            await change_balance(msg.from_user.id, row[0])
            await db.execute("DELETE FROM codes WHERE code = ?", (user_code,))
            await db.commit()
            balance = await get_balance(msg.from_user.id)
            await msg.answer(f"Код применён! Баланс пополнен на {row[0]}$. Сейчас: {balance}💎")
        else:
            await msg.answer("Неверный или уже использованный код.")

# --- Запуск ---
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())