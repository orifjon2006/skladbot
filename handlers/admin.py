from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database.models import User, Payment, Customer, OrderItem, Product
from config import ADMIN_IDS

router = Router()

# ==========================================
# 1. ADMIN VA OPERATOR FILTRI (TO'G'RILANDI)
# ==========================================
class IsAdmin(BaseFilter):
    """Bosh admin yoki bazadagi operatorlarni tekshiruvchi filtr"""
    async def __call__(self, message: Message, session: AsyncSession) -> bool:
        user_id = message.from_user.id
        
        # 1. config.py dagi asosiy adminlar
        if user_id in ADMIN_IDS:
            return True
            
        # 2. Bazadagi admin yoki operatorlar
        result = await session.execute(
            select(User).where(
                User.telegram_id == user_id, 
                User.role.in_(["admin", "operator"]) # Ikkala rolni ham taniydi
            )
        )
        return result.scalar_one_or_none() is not None

# ==========================================
# 2. FSM HOLATLARI
# ==========================================
class OperatorForm(StatesGroup):
    telegram_id = State()

# ==========================================
# 3. KLAVIATURALAR
# ==========================================
def get_admin_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📦 Mahsulotlar"), KeyboardButton(text="🛒 Savdo bo'limi")],
        [KeyboardButton(text="👥 Mijozlar"), KeyboardButton(text="💰 To'lov va Qarzlar")],
        [KeyboardButton(text="📊 Hisobotlar"), KeyboardButton(text="⚙️ Sozlamalar")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, input_field_placeholder="Kerakli bo'limni tanlang...")

def get_settings_menu() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="👨‍💻 Operatorlar ro'yxati"), KeyboardButton(text="➕ Operator qo'shish")],
        [KeyboardButton(text="◀️ Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==========================================
# 4. ADMIN PANELGA KIRISH (/admin buyrug'i)
# ==========================================
@router.message(Command("admin"), IsAdmin())
async def admin_start(message: Message, session: AsyncSession):
    # Bu faqat asosiy adminlar bazada yo'q bo'lsa ularni qo'shish uchun
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    
    if not user and message.from_user.id in ADMIN_IDS:
        new_admin = User(telegram_id=message.from_user.id, role="admin")
        session.add(new_admin)
        await session.commit()

    await message.answer(
        f"Assalomu alaykum, {message.from_user.full_name}! 🧑‍💻\n"
        f"Boshqaruv paneliga xush kelibsiz. Bo'limni tanlang:",
        reply_markup=get_admin_menu()
    )

@router.message(F.text == "◀️ Orqaga", IsAdmin())
async def back_to_main(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=get_admin_menu())

# ==========================================
# 5. HISOBOTLAR (Statistika)
# ==========================================
@router.message(F.text == "📊 Hisobotlar", IsAdmin())
async def admin_statistics(message: Message, session: AsyncSession):
    now = datetime.now()
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Bugungi tushum
    today_income = (await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.created_at >= start_of_today))).scalar()
    # Oylik tushum
    month_income = (await session.execute(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.created_at >= start_of_month))).scalar()
    # Umumiy qarz
    total_debt = abs((await session.execute(select(func.coalesce(func.sum(Customer.balance), 0)).where(Customer.balance < 0))).scalar())

    text = (
        f"📊 <b>BIZNES HISOBOTI</b>\n\n"
        f"💵 Bugun: {today_income:,.0f} so'm\n"
        f"📆 Shu oy: {month_income:,.0f} so'm\n"
        f"📉 Umumiy qarzlar: {total_debt:,.0f} so'm"
    )
    await message.answer(text)

# ==========================================
# 6. SOZLAMALAR VA OPERATORLAR
# ==========================================
@router.message(F.text == "⚙️ Sozlamalar", IsAdmin())
async def admin_settings(message: Message):
    # Faqat configdagi adminlar kirishi xavfsizroq bo'lishi mumkin
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Bu bo'limga faqat Bosh Admin kira oladi.")
        return
    await message.answer("⚙️ Sozlamalar bo'limi:", reply_markup=get_settings_menu())

@router.message(F.text == "👨‍💻 Operatorlar ro'yxati", IsAdmin())
async def list_operators(message: Message, session: AsyncSession):
    result = await session.execute(select(User).where(User.role == "operator"))
    operators = result.scalars().all()
    
    if not operators:
        await message.answer("Hozircha operatorlar yo'q.")
        return
        
    text = "👨‍💻 <b>Operatorlar:</b>\n\n"
    for op in operators:
        text += f"▪️ ID: <code>{op.telegram_id}</code>\n"
    await message.answer(text)

@router.message(F.text == "➕ Operator qo'shish", IsAdmin())
async def add_operator_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Faqat bosh admin operator qo'shishi mumkin.")
        return
    await message.answer("Yangi operatorning <b>Telegram ID</b> raqamini yozing:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OperatorForm.telegram_id)

@router.message(OperatorForm.telegram_id)
async def add_operator_finish(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text.isdigit():
        await message.answer("⚠️ Faqat raqam kiriting:")
        return
        
    tg_id = int(message.text)
    res = await session.execute(select(User).where(User.telegram_id == tg_id))
    user = res.scalar_one_or_none()
    
    if user:
        user.role = "operator"
    else:
        session.add(User(telegram_id=tg_id, role="operator"))
    
    await session.commit()
    await message.answer(f"✅ ID: {tg_id} operator sifatida saqlandi!", reply_markup=get_settings_menu())
    await state.clear()