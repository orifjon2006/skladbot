import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Customer, Payment
from handlers.admin import IsAdmin
from services.notification_service import send_payment_notification

router = Router()
logger = logging.getLogger(__name__)

# ==========================================
# 1. TO'LOV FSM HOLATLARI
# ==========================================
class PaymentForm(StatesGroup):
    customer_phone = State() # Mijozni izlash uchun
    amount = State()         # To'lanayotgan summa

# ==========================================
# 2. GLOBAL BEKOR QILISH (Har qanday qadamda ishlaydi)
# ==========================================
@router.message(Command("cancel"))
@router.message(F.text.casefold() == "bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    from handlers.admin import get_admin_menu
    await message.answer(
        "❌ Amaliyot bekor qilindi.", 
        reply_markup=get_admin_menu()
    )

# ==========================================
# 3. TO'LOV BO'LIMIGA KIRISH
# ==========================================
@router.message(F.text == "💰 To'lov va Qarzlar", IsAdmin())
async def payments_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "💰 <b>Qarz va To'lovlar bo'limi</b>\n\n"
        "To'lov qilayotgan mijozning telefon raqamini kiriting (masalan: 998901234567):\n\n"
        "<i>(Bekor qilish uchun /cancel deb yozing)</i>",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(PaymentForm.customer_phone)

# ==========================================
# 4. MIJOZNI TOPISH VA QARZINI KO'RSATISH
# ==========================================
@router.message(PaymentForm.customer_phone)
async def process_payment_customer(message: Message, state: FSMContext, session: AsyncSession):
    phone = message.text.strip().replace("+", "")
    
    # Bazadan mijozni qidiramiz
    result = await session.execute(select(Customer).where(Customer.phone == phone))
    customer = result.scalar_one_or_none()
    
    if not customer:
        await message.answer(
            "⚠️ Bunday raqamli mijoz topilmadi!\n"
            "Iltimos, raqamni qayta tekshirib kiriting yoki /cancel ni bosing:"
        )
        return
        
    await state.update_data(customer_id=customer.id)
    
    # Balans holatini chiroyli formatda chiqarish
    if customer.balance < 0:
        balance_text = f"📉 <b>Joriy qarzdorlik:</b> {abs(customer.balance):,.0f} so'm"
    elif customer.balance > 0:
        balance_text = f"📈 <b>Haqdorlik (Oldindan to'lov):</b> {customer.balance:,.0f} so'm"
    else:
        balance_text = "⚖️ <b>Qarz yo'q (Balans: 0).</b>"
        
    await message.answer(
        f"👤 <b>Mijoz:</b> {customer.name}\n"
        f"📞 <b>Telefon:</b> {customer.phone}\n"
        f"{balance_text}\n\n"
        f"💳 Mijoz qancha to'lov qilmoqda? (faqat raqam kiriting):"
    )
    await state.set_state(PaymentForm.amount)

# ==========================================
# 5. TO'LOVNI QABUL QILISH VA BAZAGA YOZISH
# ==========================================
@router.message(PaymentForm.amount)
async def process_payment_amount(message: Message, state: FSMContext, session: AsyncSession):
    # Kiritilgan summani tozalash (bo'sh joy va vergullarni olib tashlash)
    clean_val = message.text.replace(" ", "").replace(",", "").replace("'", "")
    
    try:
        amount = float(clean_val)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Iltimos, to'lov summasini noldan katta raqam shaklida kiriting (masalan: 50000):")
        return
        
    data = await state.get_data()
    customer_id = data['customer_id']
    
    try:
        # Mijozni bazadan yangitdan olamiz (oxirgi holatini bilish uchun)
        customer = await session.get(Customer, customer_id)
        if not customer:
            raise Exception("Mijoz topilmadi")

        # 1. Balansni yangilaymiz
        customer.balance += amount
        
        # 2. To'lov tarixini yaratamiz
        payment = Payment(customer_id=customer.id, amount=amount)
        session.add(payment)
        
        # 3. Bazaga saqlaymiz
        await session.commit()
        
        # Yangi holat matni
        if customer.balance < 0:
            new_status = f"Qolgan qarz: {abs(customer.balance):,.0f} so'm"
        else:
            new_status = f"Ortiqcha to'lov: {customer.balance:,.0f} so'm"

        from handlers.admin import get_admin_menu
        await message.answer(
            f"✅ <b>To'lov qabul qilindi!</b>\n\n"
            f"👤 Mijoz: {customer.name}\n"
            f"💵 Summa: {amount:,.0f} so'm\n"
            f"💳 Yangi holat: {new_status}",
            reply_markup=get_admin_menu()
        )
        
        # 4. MIJOZGA AVTOMATIK BILDIRISHNOMA
        await send_payment_notification(message.bot, customer, amount)
        
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.error(f"To'lovni saqlashda xato: {e}")
        await message.answer("❌ Xatolik yuz berdi. To'lov saqlanmadi.")
        await state.clear()