import logging

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database.models import Customer, Order, Payment
from handlers.admin import IsAdmin
from services.notification_service import send_payment_notification

router = Router()
logger = logging.getLogger(__name__)


class PaymentForm(StatesGroup):
    receipt_code = State()
    amount = State()


def format_money(amount: float) -> str:
    return f"{amount:,.0f} so'm"


async def get_total_paid_for_order(session: AsyncSession, order_id: int) -> float:
    result = await session.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.order_id == order_id)
    )
    total_paid = result.scalar_one()
    return float(total_paid or 0)


@router.message(Command("cancel"))
@router.message(F.text.casefold() == "bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    from handlers.admin import get_admin_menu
    await message.answer("❌ Amaliyot bekor qilindi.", reply_markup=get_admin_menu())


@router.message(F.text == "💰 To'lov va Qarzlar", IsAdmin())
async def payments_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💰 <b>Qarz va To'lovlar bo'limi</b>\n\n"
        "Mijoz bergan <b>xarid kodini</b> kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(PaymentForm.receipt_code)


@router.message(PaymentForm.receipt_code)
async def process_payment_receipt_code(message: Message, state: FSMContext, session: AsyncSession):
    receipt_code = message.text.strip().upper()

    result = await session.execute(
        select(Order).where(Order.receipt_code == receipt_code)
    )
    order = result.scalar_one_or_none()

    if not order:
        await message.answer(
            "⚠️ Bunday xarid kod topilmadi!\n"
            "Kodni qayta kiriting yoki /cancel ni bosing:"
        )
        return

    customer = await session.get(Customer, order.customer_id)
    if not customer:
        await message.answer("❌ Ushbu kodga bog'langan mijoz topilmadi.")
        return

    total_paid = await get_total_paid_for_order(session, order.id)
    total_price = float(order.total_price or 0)
    remaining_debt = max(total_price - total_paid, 0)
    overpaid = max(total_paid - total_price, 0)

    text = (
        f"🔑 <b>Xarid kodi:</b> <code>{receipt_code}</code>\n"
        f"👤 <b>Mijoz:</b> {customer.name}\n"
        f"📞 <b>Telefon:</b> {customer.phone}\n"
        f"💰 <b>Jami summa:</b> {format_money(total_price)}\n"
        f"💵 <b>Jami to'langan:</b> {format_money(total_paid)}\n"
        f"📉 <b>Qolgan qarz:</b> {format_money(remaining_debt)}"
    )

    if overpaid > 0:
        text += f"\n📈 <b>Ortiqcha to'lov:</b> {format_money(overpaid)}"

    text += "\n\n💳 Endi qancha to'lov qilmoqda? (faqat raqam kiriting):"

    await state.update_data(order_id=order.id, customer_id=customer.id, receipt_code=receipt_code)
    await message.answer(text)
    await state.set_state(PaymentForm.amount)


@router.message(PaymentForm.amount)
async def process_payment_amount(message: Message, state: FSMContext, session: AsyncSession):
    clean_val = message.text.replace(" ", "").replace(",", "").replace("'", "")

    try:
        amount = float(clean_val)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(
            "⚠️ Iltimos, to'lov summasini noldan katta raqam shaklida kiriting "
            "(masalan: 50000):"
        )
        return

    data = await state.get_data()
    order_id = data["order_id"]
    customer_id = data["customer_id"]
    receipt_code = data["receipt_code"]

    try:
        order = await session.get(Order, order_id)
        customer = await session.get(Customer, customer_id)

        if not order:
            raise Exception("Buyurtma topilmadi.")
        if not customer:
            raise Exception("Mijoz topilmadi.")

        payment = Payment(
            customer_id=customer.id,
            order_id=order.id,
            amount=amount
        )
        session.add(payment)

        current_balance = float(customer.balance or 0)
        customer.balance = current_balance + amount

        await session.commit()
        await session.refresh(customer)

        total_paid = await get_total_paid_for_order(session, order.id)
        total_price = float(order.total_price or 0)
        remaining_debt = max(total_price - total_paid, 0)
        overpaid = max(total_paid - total_price, 0)

        text = (
            f"✅ <b>To'lov qabul qilindi!</b>\n\n"
            f"🔑 Kod: <code>{receipt_code}</code>\n"
            f"👤 Mijoz: {customer.name}\n"
            f"💵 Qabul qilingan summa: {format_money(amount)}\n"
            f"💰 Jami to'langan: {format_money(total_paid)}\n"
            f"📉 Qolgan qarz: {format_money(remaining_debt)}"
        )

        if overpaid > 0:
            text += f"\n📈 Ortiqcha to'lov: {format_money(overpaid)}"

        text += f"\n💳 Mijoz umumiy balansi: {format_money(float(customer.balance or 0))}"

        from handlers.admin import get_admin_menu
        await message.answer(text, reply_markup=get_admin_menu())

        await send_payment_notification(message.bot, customer, amount)
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.exception("To'lovni saqlashda xato")
        await message.answer(f"❌ Xatolik yuz berdi. To'lov saqlanmadi: {str(e)}")
        await state.clear()
