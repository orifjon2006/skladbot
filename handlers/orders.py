import logging
import random
import string

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Product, Customer, Order, OrderItem, Payment
from handlers.admin import IsAdmin
from services.notification_service import send_receipt

router = Router()
logger = logging.getLogger(__name__)


class OrderForm(StatesGroup):
    customer_phone = State()
    product_code = State()
    quantity = State()
    cart_action = State()
    payment = State()


def cart_menu_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="➕ Yana mahsulot qo'shish")],
        [KeyboardButton(text="💳 To'lovga o'tish"), KeyboardButton(text="❌ Xaridni bekor qilish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def format_money(amount: float) -> str:
    return f"{amount:,.0f} so'm"


async def generate_unique_receipt_code(session: AsyncSession, length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits

    while True:
        code = "".join(random.choices(alphabet, k=length))
        result = await session.execute(
            select(Order).where(Order.receipt_code == code)
        )
        exists = result.scalar_one_or_none()
        if not exists:
            return code


@router.message(Command("cancel"))
@router.message(F.text == "❌ Xaridni bekor qilish")
async def cancel_order_process(message: Message, state: FSMContext):
    await state.clear()
    from handlers.admin import get_admin_menu
    await message.answer(
        "🗑 Xarid jarayoni bekor qilindi. Savat xotiradan tozalandi.",
        reply_markup=get_admin_menu()
    )


@router.message(F.text == "🛒 Savdo bo'limi", IsAdmin())
async def start_order(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(cart={}, total_sum=0)

    await message.answer(
        "🛒 <b>Yangi xarid rasmiylashtirish:</b>\n\n"
        "Mijozning telefon raqamini kiriting (masalan: 998901234567):\n"
        "<i>(Noma'lum mijoz uchun 0 ni bosing)</i>",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(OrderForm.customer_phone)


@router.message(OrderForm.customer_phone)
async def process_customer(message: Message, state: FSMContext, session: AsyncSession):
    phone = message.text.strip().replace("+", "")

    if phone == "0":
        phone = "Noma'lum"
        customer_name = "Umumiy Mijoz"
    else:
        customer_name = f"Mijoz {phone}"

    result = await session.execute(select(Customer).where(Customer.phone == phone))
    customer = result.scalar_one_or_none()

    if not customer:
        customer = Customer(name=customer_name, phone=phone)
        session.add(customer)
        await session.commit()
        await session.refresh(customer)

    await state.update_data(customer_id=customer.id)
    await message.answer(
        f"👤 Mijoz: <b>{customer.name}</b>\n\n"
        f"🔍 Sotiladigan <b>mahsulot kodini</b> kiriting:"
    )
    await state.set_state(OrderForm.product_code)


@router.message(OrderForm.product_code)
async def process_product_code(message: Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip()

    result = await session.execute(select(Product).where(Product.code == code))
    product = result.scalar_one_or_none()

    if not product:
        await message.answer("⚠️ Mahsulot topilmadi! Qayta kiriting yoki /cancel bosing:")
        return

    if product.quantity <= 0:
        await message.answer(f"❌ <b>{product.name}</b> tugagan! Boshqa kod kiriting:")
        return

    await state.update_data(
        current_product_id=product.id,
        current_product_name=product.name,
        max_qty=product.quantity,
        current_price=product.price
    )

    await message.answer(
        f"📦 Mahsulot: <b>{product.name}</b>\n"
        f"📊 Qoldiq: {product.quantity} ta | Narxi: {product.price:,.0f} so'm\n\n"
        f"🔢 Nechta sotilmoqda?:"
    )
    await state.set_state(OrderForm.quantity)


@router.message(OrderForm.quantity)
async def process_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Faqat raqam kiriting:")
        return

    qty = int(message.text)
    data = await state.get_data()

    if qty <= 0 or qty > data["max_qty"]:
        await message.answer(f"⚠️ Xato! 1 dan {data['max_qty']} gacha raqam kiriting:")
        return

    cart = data.get("cart", {})
    prod_id = data["current_product_id"]

    if str(prod_id) in cart:
        cart[str(prod_id)]["qty"] += qty
    else:
        cart[str(prod_id)] = {
            "id": prod_id,
            "name": data["current_product_name"],
            "price": data["current_price"],
            "qty": qty
        }

    total_sum = sum(item["price"] * item["qty"] for item in cart.values())
    await state.update_data(cart=cart, total_sum=total_sum)

    cart_msg = "🛒 <b>Savat tarkibi:</b>\n\n"
    for item in cart.values():
        cart_msg += (
            f"▪️ {item['name']} x {item['qty']} = "
            f"{item['price'] * item['qty']:,.0f} so'm\n"
        )
    cart_msg += f"\n💵 <b>Jami: {total_sum:,.0f} so'm</b>"

    await message.answer(cart_msg, reply_markup=cart_menu_kb())
    await state.set_state(OrderForm.cart_action)


@router.message(OrderForm.cart_action, F.text == "➕ Yana mahsulot qo'shish")
async def add_more(message: Message, state: FSMContext):
    await message.answer("🔍 Mahsulot kodini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderForm.product_code)


@router.message(OrderForm.cart_action, F.text == "💳 To'lovga o'tish")
async def go_pay(message: Message, state: FSMContext):
    data = await state.get_data()
    total = data.get("total_sum", 0)

    await message.answer(
        f"💵 Jami: <b>{total:,.0f} so'm</b>\n\n"
        f"Mijoz to'lagan summa (faqat raqam):",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(OrderForm.payment)


@router.message(OrderForm.payment)
async def finalize_order(message: Message, state: FSMContext, session: AsyncSession):
    try:
        val = message.text.replace(" ", "").replace(",", "").replace("'", "")
        paid_amount = float(val)

        if paid_amount < 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Faqat musbat raqam kiriting (masalan: 50000):")
        return

    data = await state.get_data()
    cart = data.get("cart", {})
    total_sum = data.get("total_sum", 0)
    customer_id = data.get("customer_id")

    if not cart:
        await message.answer("⚠️ Savat bo'sh. Xaridni qaytadan boshlang.")
        await state.clear()
        return

    try:
        customer = await session.get(Customer, customer_id)
        if not customer:
            raise Exception("Mijoz topilmadi.")

        generated_code = await generate_unique_receipt_code(session)

        new_order = Order(
            customer_id=customer.id,
            total_price=total_sum,
            status="delivered",
            receipt_code=generated_code
        )
        session.add(new_order)
        await session.flush()

        receipt_text = ""
        for item in cart.values():
            product = await session.get(Product, item["id"])
            if not product:
                raise Exception("Mahsulot topilmadi.")
            if product.quantity < item["qty"]:
                raise Exception(f"{product.name} yetarli emas!")

            product.quantity -= item["qty"]

            order_item = OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                quantity=item["qty"],
                price=item["price"]
            )
            session.add(order_item)
            receipt_text += f"- {item['name']} x {item['qty']} ta\n"

        if paid_amount > 0:
            payment = Payment(
                customer_id=customer.id,
                order_id=new_order.id,
                amount=paid_amount
            )
            session.add(payment)

        # Umumiy balans:
        # balans = eski balans - order summasi + to'lov
        current_balance = float(customer.balance or 0)
        customer.balance = current_balance - total_sum + paid_amount

        remaining_debt = max(total_sum - paid_amount, 0)
        overpaid = max(paid_amount - total_sum, 0)

        await session.commit()
        await session.refresh(customer)

        extra_text = ""
        if overpaid > 0:
            extra_text = f"\n📈 Ortiqcha to'lov: {format_money(overpaid)}"

        final_text = (
            f"✅ <b>Xarid yakunlandi!</b>\n\n"
            f"🔑 <b>MIJOZ UCHUN KOD:</b> <code>{generated_code}</code>\n\n"
            f"💰 Jami: {format_money(total_sum)}\n"
            f"💵 To'landi: {format_money(paid_amount)}\n"
            f"📉 Qolgan qarz: {format_money(remaining_debt)}"
            f"{extra_text}\n"
            f"💳 Mijoz balansi: {format_money(customer.balance)}"
        )

        from handlers.admin import get_admin_menu
        await message.answer(final_text, reply_markup=get_admin_menu())

        await send_receipt(
            bot=message.bot,
            customer=customer,
            total_price=total_sum,
            paid_amount=paid_amount,
            debt=remaining_debt,
            products_text=receipt_text,
            receipt_code=generated_code
        )

        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.exception("Xaridda xatolik")
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")
        await state.clear()
