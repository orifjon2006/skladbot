import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload, joinedload # <--- joinedload qo'shildi

from database.models import Customer, User, Order, Product, OrderItem # <--- OrderItem qo'shildi
from config import ADMIN_IDS

router = Router()
logger = logging.getLogger(__name__)
router = Router()

# ==========================================
# 1. MIJOZ HOLATLARI (FSM)
# ==========================================
class ClientState(StatesGroup):
    waiting_for_code = State() # 6 talik kodni kutish

# ==========================================
# 2. KLAVIATURALAR
# ==========================================
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

# ==========================================
# 3. YAGONA START BUYRUG'I
# ==========================================
@router.message(CommandStart())
async def unified_start(message: Message, session: AsyncSession):
    user_id = message.from_user.id
    
    if user_id in ADMIN_IDS:
        from handlers.admin import get_admin_menu
        await message.answer("Xush kelibsiz, Bosh Admin! 🧑‍💻", reply_markup=get_admin_menu())
        return

    res = await session.execute(select(User).where(User.telegram_id == user_id, User.role == "operator"))
    if res.scalar_one_or_none():
        from handlers.admin import get_admin_menu
        await message.answer("Xush kelibsiz, Operator! 👷‍♂️", reply_markup=get_admin_menu())
        return

    res = await session.execute(select(Customer).where(Customer.telegram_id == user_id))
    customer = res.scalar_one_or_none()

    if customer:
        await message.answer(f"Xush kelibsiz, {customer.name}! 👋", reply_markup=get_customer_main_menu())
    else:
        await message.answer(
            "Assalomu alaykum! <b>BIOFIT</b> tizimiga xush kelibsiz.\n\n"
            "Cheklaringizni onlayn qabul qilish uchun telefon raqamingizni tasdiqlang:",
            reply_markup=get_contact_kb()
        )

# ==========================================
# 4. KONTAKT QABUL QILISH VA KOD SO'RASH
# ==========================================
@router.message(F.contact)
async def handle_contact(message: Message, state: FSMContext, session: AsyncSession):
    phone = message.contact.phone_number.replace("+", "").strip()
    user_id = message.from_user.id

    res = await session.execute(select(Customer).where(Customer.phone == phone))
    customer = res.scalar_one_or_none()

    if customer:
        customer.telegram_id = user_id
        await session.commit()
    else:
        new_c = Customer(name=message.from_user.full_name, phone=phone, telegram_id=user_id)
        session.add(new_c)
        await session.commit()
        
    # Raqam tasdiqlangach, darhol kod so'raymiz
    await message.answer(
        "✅ <b>Raqamingiz muvaffaqiyatli tasdiqlandi!</b>\n\n"
        "Agar sizda do'konimiz tomonidan berilgan <b>6 talik xarid kodi</b> bo'lsa, uni hozir kiriting:\n"
        "<i>(Agar kod bo'lmasa, pastdagi tugmani bosing)</i>",
        reply_markup=cancel_code_kb()
    )
    await state.set_state(ClientState.waiting_for_code)

# ==========================================
# 5. XARID KODINI TEKSHIRISH
# ==========================================
@router.message(F.text == "🧾 Xarid kodini kiritish")
async def ask_for_code_btn(message: Message, state: FSMContext):
    await message.answer("🔑 <b>6 talik xarid kodini kiriting:</b>", reply_markup=cancel_code_kb())
    await state.set_state(ClientState.waiting_for_code)

@router.message(ClientState.waiting_for_code, F.text == "❌ Bekor qilish")
async def cancel_code_input(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyuga qaytdik.", reply_markup=get_customer_main_menu())

@router.message(ClientState.waiting_for_code)
async def process_receipt_code(message: Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip().upper() # Kodni katta harflarga o'giramiz
    
    # Bazadan shu kodli buyurtmani va uning ichidagi mahsulotlarni qidiramiz
    result = await session.execute(
        select(Order)
        .where(Order.receipt_code == code)
        .options(selectinload(Order.items).joinedload(OrderItem.product))
    )
    order = result.scalar_one_or_none()
    
    if not order:
        await message.answer("⚠️ <b>Xato kod!</b> Bunday xarid kodi topilmadi. Qaytadan urinib ko'ring yoki bekor qiling:")
        return
        
    # Agar topilsa, chiroyli chek shakllantiramiz
    receipt = f"🧾 <b>Sizning xarid chekingiz (Kod: {code})</b>\n"
    receipt += f"📅 Sana: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
    receipt += "📦 <b>Xarid qilingan mahsulotlar:</b>\n"
    
    for item in order.items:
        receipt += f"▪️ {item.product.name} — {item.quantity} ta x {item.price:,.0f} so'm\n"
        
    receipt += f"\n💰 <b>Jami summa:</b> {order.total_price:,.0f} so'm\n"
    receipt += "✅ <i>Xaridingiz uchun rahmat! Endi yangi xaridlar xabari sizga avtomatik kelib turadi.</i>"
    
    await message.answer(receipt, reply_markup=get_customer_main_menu())
    await state.clear()

# ==========================================
# 6. QARZNI KO'RISH
# ==========================================
@router.message(F.text == "📊 Mening qarzim")
async def check_my_debt(message: Message, session: AsyncSession):
    result = await session.execute(select(Customer).where(Customer.telegram_id == message.from_user.id))
    customer = result.scalar_one_or_none()
    
    if customer:
        if customer.balance < 0:
            text = f"📉 Sizning joriy qarzingiz: <b>{abs(customer.balance):,.0f} so'm</b>"
        elif customer.balance > 0:
            text = f"📈 Sizda <b>{customer.balance:,.0f} so'm</b> ortiqcha to'lov (haqdorlik) mavjud."
        else:
            text = "✅ Sizning qarzingiz yo'q."
        await message.answer(text)
# ==========================================
# 6.5 XARIDLAR TARIXINI KO'RISH
# ==========================================
@router.message(F.text == "📜 Xaridlar tarixi")
async def view_purchase_history(message: Message, session: AsyncSession):
    # 1. Mijozni aniqlaymiz
    result = await session.execute(
        select(Customer).where(Customer.telegram_id == message.from_user.id)
    )
    customer = result.scalar_one_or_none()
    
    if not customer:
        await message.answer("Sizning ma'lumotlaringiz topilmadi. Iltimos, /start ni bosing.")
        return

    # 2. Mijozning oxirgi 5 ta xaridini bazadan tortib olamiz
    orders_result = await session.execute(
        select(Order)
        .where(Order.customer_id == customer.id)
        .options(selectinload(Order.items).joinedload(OrderItem.product))
        .order_by(Order.created_at.desc()) # Eng yangilari birinchi chiqadi
        .limit(5) # Faqat oxirgi 5 tasini ko'rsatamiz (ekran to'lib ketmasligi uchun)
    )
    orders = orders_result.scalars().all()

    # Agar umuman xarid qilmagan bo'lsa:
    if not orders:
        await message.answer("🤷‍♂️ Sizda hali xaridlar tarixi yo'q.")
        return

    # 3. Tarixni chiroyli matn shakliga keltiramiz
    text = "📜 <b>Sizning oxirgi xaridlaringiz:</b>\n\n"
    for i, order in enumerate(orders, 1):
        date_str = order.created_at.strftime("%d.%m.%Y %H:%M")
        code_str = order.receipt_code if order.receipt_code else "Yo'q"
        
        text += f"🛍 <b>{i}-xarid (Kod: {code_str})</b>\n"
        text += f"📅 Sana: {date_str}\n"
        
        for item in order.items:
            text += f" ▪️ {item.product.name} - {item.quantity} ta x {item.price:,.0f} so'm\n"
            
        text += f"💰 <b>Jami: {order.total_price:,.0f} so'm</b>\n"
        text += "〰️〰️〰️〰️〰️〰️〰️〰️\n"

    await message.answer(text)
# ==========================================
# 7. TUSHUNARSIZ XABARLARNI USHLOVCHI (CATCH-ALL)
# ==========================================
@router.message()
async def catch_all_messages(message: Message):
    await message.answer(
        "Kechirasiz, men bu xabaringizni tushunmadim. 🤖\n\n"
        "Iltimos, botni qayta ishga tushirish uchun /start buyrug'ini bosing yoki menyudagi tugmalardan foydalaning."
    )