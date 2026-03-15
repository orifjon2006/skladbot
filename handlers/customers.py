from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Customer
from handlers.admin import IsAdmin

router = Router()

# ==========================================
# 1. MIJOZ QIDIRISH UCHUN FSM HOLATI
# ==========================================
class CustomerSearch(StatesGroup):
    phone = State()

# ==========================================
# 2. MIJOZLAR MENYUSI
# ==========================================
def customers_menu_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="👥 Barcha mijozlar"), KeyboardButton(text="📉 Qarzdorlar ro'yxati")],
        [KeyboardButton(text="🔍 Mijozni qidirish"), KeyboardButton(text="◀️ Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# Admindagi "👥 Mijozlar" tugmasi bosilganda
@router.message(F.text == "👥 Mijozlar", IsAdmin())
async def customers_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("👥 <b>Mijozlar bo'limi</b>\n\nNima ish qilamiz?", reply_markup=customers_menu_kb())

# ==========================================
# 3. BARCHA MIJOZLARNI KO'RISH
# ==========================================
@router.message(F.text == "👥 Barcha mijozlar", IsAdmin())
async def list_all_customers(message: Message, session: AsyncSession):
    # Bazadan barcha mijozlarni ismiga qarab tartiblab olamiz
    result = await session.execute(select(Customer).order_by(Customer.name))
    customers = result.scalars().all()

    if not customers:
        await message.answer("📭 Hozircha bazada mijozlar yo'q.")
        return

    text = "👥 <b>Barcha mijozlar ro'yxati:</b>\n\n"
    for c in customers:
        # Balansni chiroyli ko'rsatish
        if c.balance < 0:
            bal = f"Qarz: {abs(c.balance):,.0f} so'm 🔴"
        elif c.balance > 0:
            bal = f"Haqdor: {c.balance:,.0f} so'm 🟢"
        else:
            bal = "Qarzi yo'q ⚪️"
            
        text += f"👤 <b>{c.name}</b> (📞 {c.phone})\n   {bal}\n\n"
    
    # Matn juda uzun bo'lib ketsa, Telegram xato bermasligi uchun qirqib yuboramiz
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x+4000])
    else:
        await message.answer(text)

# ==========================================
# 4. QARZDORLAR RO'YXATI
# ==========================================
@router.message(F.text == "📉 Qarzdorlar ro'yxati", IsAdmin())
async def list_debtors(message: Message, session: AsyncSession):
    # Faqat balansi 0 dan kichik (manfiy) bo'lganlarni olamiz
    result = await session.execute(select(Customer).where(Customer.balance < 0).order_by(Customer.balance))
    debtors = result.scalars().all()

    if not debtors:
        await message.answer("🎉 Ajoyib! Hozircha hech kimning qarzi yo'q.")
        return

    total_debt = sum(abs(d.balance) for d in debtors)
    
    text = f"📉 <b>Qarzdor mijozlar ro'yxati:</b>\n"
    text += f"💸 Umumiy haqqimiz: <b>{total_debt:,.0f} so'm</b>\n\n"
    
    for d in debtors:
        text += f"👤 <b>{d.name}</b> (📞 {d.phone})\n   Qarz: {abs(d.balance):,.0f} so'm\n\n"
    
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x+4000])
    else:
        await message.answer(text)

# ==========================================
# 5. MIJOZNI QIDIRISH (FSM)
# ==========================================
@router.message(F.text == "🔍 Mijozni qidirish", IsAdmin())
async def search_customer_start(message: Message, state: FSMContext):
    await message.answer(
        "🔍 Izlayotgan mijozingizning <b>telefon raqamini</b> kiriting:\n"
        "<i>(Bekor qilish uchun /cancel bosishingiz mumkin)</i>",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(CustomerSearch.phone)

@router.message(CustomerSearch.phone)
async def process_customer_search(message: Message, state: FSMContext, session: AsyncSession):
    phone = message.text.strip()
    
    result = await session.execute(select(Customer).where(Customer.phone.contains(phone)))
    customers = result.scalars().all()
    
    if not customers:
        await message.answer("⚠️ Bunday raqamli mijoz topilmadi. Boshqa raqam kiriting yoki /cancel ni bosing:")
        return
        
    text = "🔍 <b>Qidiruv natijalari:</b>\n\n"
    for c in customers:
        if c.balance < 0:
            bal = f"Qarz: {abs(c.balance):,.0f} so'm"
        else:
            bal = f"Balans: {c.balance:,.0f} so'm"
            
        text += f"👤 <b>{c.name}</b>\n📞 Telefon: {c.phone}\n💳 {bal}\n\n"
        
    await message.answer(text, reply_markup=customers_menu_kb())
    await state.clear()