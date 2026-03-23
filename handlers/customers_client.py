import logging

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from database.models import Customer, User, Order, OrderItem, Payment
from config import ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)


class ClientState(StatesGroup):
    waiting_for_code = State()
    waiting_for_debt_code = State()


def get_contact_kb() -> ReplyKeyboardMarkup:
    kb = [[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)


def get_customer_main_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🧾 Xarid kodini kiritish")],
        [KeyboardButton(text="📊 Mening qarzim"), KeyboardButton(text="📜 Xaridlar tarixi")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def cancel_code_kb() -> ReplyKeyboardMarkup:
    kb = [[KeyboardButton(text="❌ Bekor qilish")]]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def format_money(amount: float) -> str:
    return f"{amount:,.0f} so'm"


async def get_customer_by_telegram_id(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(Customer).where(Customer.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_total_paid_for_order(session: AsyncSession, order_id: int) -> float:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.order_id == order_id)
    )
    total_paid = result.scalar_one()
    return float(total_paid or 0)


@router.message(CommandStart())
async def unified_start(message: Message, session: AsyncSession):
    user_id = message.from_user.id

    if user_id in ADMIN_IDS:
        from handlers.admin import get_admin_menu
        await message.answer("Xush kelibsiz, Bosh Admin! 🧑‍💻", reply_markup=get_admin_menu())
        return

    res = await session.execute(
        select(User).where(User.telegram_id == user_id, User.role == "operator")
    )
    if res.scalar_one_or_none():
        from handlers.admin import get_admin_menu
        await message.answer("Xush kelibsiz, Operator! 👷‍♂️", reply_markup=get_admin_menu())
        return

    customer = await get_customer_by_telegram_id(session, user_id)

    if customer:
        await message.answer(
            f"Xush kelibsiz, {customer.name}! 👋",
            reply_markup=get_customer_main_menu()
        )
    else:
        await message.answer(
            "Assalomu alaykum! <b>BIOFIT</b> tizimiga xush kelibsiz.\n\n"
            "Cheklaringizni onlayn ko'rish uchun telefon raqamingizni tasdiqlang:",
            reply_markup=get_contact_kb()
        )


@router.message(F.contact)
async def handle_contact(message: Message, state: FSMContext, session: AsyncSession):
    phone = message.contact.phone_number.replace("+", "").strip()
    user_id = message.from_user.id

    result = await session.execute(select(Customer).where(Customer.phone == phone))
    customer = result.scalar_one_or_none()

    if customer:
        customer.telegram_id = user_id
        await session.commit()
    else:
        new_customer = Customer(
            name=message.from_user.full_name,
            phone=phone,
            telegram_id=user_id
        )
        session.add(new_customer)
        await session.commit()

    await message.answer(
        "✅ <b>Raqamingiz muvaffaqiyatli tasdiqlandi!</b>\n\n"
        "Endi do'kon tomonidan berilgan <b>xarid kodini</b> kiritsangiz, "
        "chekingiz va qarzingizni ko'rishingiz mumkin.",
        reply_markup=get_customer_main_menu()
    )
    await state.clear()


@router.message(Command("cancel"))
@router.message(F.text == "❌ Bekor qilish")
async def cancel_code_input(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyuga qaytdik.", reply_markup=get_customer_main_menu())


@router.message(F.text == "🧾 Xarid kodini kiritish")
async def ask_for_code_btn(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🔑 <b>Xarid kodini kiriting:</b>",
        reply_markup=cancel_code_kb()
    )
    await state.set_state(ClientState.waiting_for_code)


@router.message(ClientState.waiting_for_code)
async def process_receipt_code(message: Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip().upper()

    customer = await get_customer_by_telegram_id(session, message.from_user.id)
    if not customer:
        await message.answer(
            "Sizning profilingiz topilmadi. Iltimos, /start ni bosing.",
            reply_markup=get_contact_kb()
        )
        await state.clear()
        return

    result = await session.execute(
        select(Order)
        .where(
            Order.receipt_code == code,
            Order.customer_id == customer.id
        )
        .options(selectinload(Order.items).selectinload(OrderItem.product))
    )
    order = result.scalar_one_or_none()

    if not order:
        await message.answer(
            "⚠️ <b>Bunday xarid kodi topilmadi.</b>\n"
            "Kod xato bo'lishi mumkin yoki u sizning profilingizga bog'lanmagan.\n\n"
            "Qaytadan urinib ko'ring yoki bekor qiling:"
        )
        return

    total_paid = await get_total_paid_for_order(session, order.id)
    total_price = float(order.total_price or 0)
    remaining_debt = max(total_price - total_paid, 0)
    overpaid = max(total_paid - total_price, 0)

    receipt = f"🧾 <b>Sizning xarid chekingiz</b>\n"
    receipt += f"🔑 Kod: <code>{code}</code>\n"
    if order.created_at:
        receipt += f"📅 Sana: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    receipt += "\n📦 <b>Xarid qilingan mahsulotlar:</b>\n"

    if order.items:
        for item in order.items:
            product_name = item.product.name if item.product else "Noma'lum mahsulot"
            receipt += (
                f"▪️ {product_name} — {item.quantity} ta x "
                f"{float(item.price):,.0f} so'm\n"
            )
    else:
        receipt += "▪️ Mahsulotlar topilmadi\n"

    receipt += f"\n💰 <b>Jami summa:</b> {format_money(total_price)}"
    receipt += f"\n💵 <b>Jami to'langan:</b> {format_money(total_paid)}"
    receipt += f"\n📉 <b>Qolgan qarz:</b> {format_money(remaining_debt)}"

    if overpaid > 0:
        receipt += f"\n📈 <b>Ortiqcha to'lov:</b> {format_money(overpaid)}"

    receipt += "\n\n✅ <i>Ma'lumot muvaffaqiyatli topildi.</i>"

    await message.answer(receipt, reply_markup=get_customer_main_menu())
    await state.clear()


@router.message(F.text == "📊 Mening qarzim")
async def ask_for_debt_code(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📊 <b>Qarzni ko'rish uchun xarid kodini kiriting:</b>",
        reply_markup=cancel_code_kb()
    )
    await state.set_state(ClientState.waiting_for_debt_code)


@router.message(ClientState.waiting_for_debt_code)
async def check_my_debt_by_code(message: Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip().upper()

    customer = await get_customer_by_telegram_id(session, message.from_user.id)
    if not customer:
        await message.answer(
            "Sizning profilingiz topilmadi. Iltimos, /start ni bosing.",
            reply_markup=get_contact_kb()
        )
        await state.clear()
        return

    result = await session.execute(
        select(Order).where(
            Order.receipt_code == code,
            Order.customer_id == customer.id
        )
    )
    order = result.scalar_one_or_none()

    if not order:
        await message.answer(
            "⚠️ Bu kod bo'yicha qarz ma'lumoti topilmadi.\n"
            "Kod xato bo'lishi mumkin yoki u sizning profilingizga tegishli emas."
        )
        return

    total_paid = await get_total_paid_for_order(session, order.id)
    total_price = float(order.total_price or 0)
    remaining_debt = max(total_price - total_paid, 0)
    overpaid = max(total_paid - total_price, 0)

    text = (
        f"📊 <b>Qarz ma'lumoti</b>\n"
        f"🔑 Kod: <code>{code}</code>\n"
        f"💰 Jami summa: {format_money(total_price)}\n"
        f"💵 Jami to'langan: {format_money(total_paid)}\n"
        f"📉 Qolgan qarz: {format_money(remaining_debt)}"
    )

    if overpaid > 0:
        text += f"\n📈 Ortiqcha to'lov: {format_money(overpaid)}"

    await message.answer(text, reply_markup=get_customer_main_menu())
    await state.clear()


@router.message(F.text == "📜 Xaridlar tarixi")
async def view_purchase_history(message: Message, session: AsyncSession):
    customer = await get_customer_by_telegram_id(session, message.from_user.id)

    if not customer:
        await message.answer("Sizning ma'lumotlaringiz topilmadi. Iltimos, /start ni bosing.")
        return

    orders_result = await session.execute(
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(selectinload(Order.items).selectinload(OrderItem.product))
        .order_by(Order.created_at.desc())
        .limit(5)
    )
    orders = orders_result.scalars().all()

    if not orders:
        await message.answer("🤷‍♂️ Sizda hali xaridlar tarixi yo'q.")
        return

    order_ids = [order.id for order in orders]

    payments_result = await session.execute(
        select(
            Payment.order_id,
            func.coalesce(func.sum(Payment.amount), 0)
        )
        .where(Payment.order_id.in_(order_ids))
        .group_by(Payment.order_id)
    )
    paid_map = {
        order_id: float(total_paid or 0)
        for order_id, total_paid in payments_result.all()
    }

    text = "📜 <b>Sizning oxirgi xaridlaringiz:</b>\n\n"

    for i, order in enumerate(orders, 1):
        date_str = order.created_at.strftime("%d.%m.%Y %H:%M") if order.created_at else "-"
        code_str = order.receipt_code if order.receipt_code else "Yo'q"

        total_price = float(order.total_price or 0)
        total_paid = paid_map.get(order.id, 0.0)
        remaining_debt = max(total_price - total_paid, 0)

        text += f"🛍 <b>{i}-xarid</b>\n"
        text += f"🔑 Kod: <code>{code_str}</code>\n"
        text += f"📅 Sana: {date_str}\n"

        if order.items:
            for item in order.items:
                product_name = item.product.name if item.product else "Noma'lum mahsulot"
                text += (
                    f" ▪️ {product_name} - {item.quantity} ta x "
                    f"{float(item.price):,.0f} so'm\n"
                )

        text += f"💰 Jami: {format_money(total_price)}\n"
        text += f"💵 To'langan: {format_money(total_paid)}\n"
        text += f"📉 Qarz: {format_money(remaining_debt)}\n"
        text += "〰️〰️〰️〰️〰️〰️〰️〰️\n"

    await message.answer(text, reply_markup=get_customer_main_menu())


@router.message()
async def catch_all_messages(message: Message):
    await message.answer(
        "Kechirasiz, men bu xabaringizni tushunmadim. 🤖\n\n"
        "Iltimos, /start ni bosing yoki menyudagi tugmalardan foydalaning."
    )
