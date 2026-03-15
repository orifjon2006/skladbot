import logging
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.models import Product
from handlers.admin import IsAdmin 

router = Router()
logger = logging.getLogger(__name__)

# ==========================================
# 1. FSM HOLATLARI 
# ==========================================
class ProductForm(StatesGroup):
    name = State()      # Mahsulot nomi
    code = State()      # Mahsulot kodi
    quantity = State()  # Boshlang'ich soni
    price = State()     # Sotilish narxi

class DeleteProductForm(StatesGroup):
    code = State()      # O'chiriladigan mahsulot kodi

# ==========================================
# 2. MAHSULOTLAR MENYUSI
# ==========================================
def products_menu_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="➕ Yangi mahsulot qo'shish"), KeyboardButton(text="📋 Mahsulotlar ro'yxati")],
        [KeyboardButton(text="🔍 Qidirish"), KeyboardButton(text="🗑 Mahsulotni o'chirish")],
        [KeyboardButton(text="◀️ Orqaga")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@router.message(F.text == "📦 Mahsulotlar", IsAdmin())
async def products_menu(message: Message):
    await message.answer("📦 <b>Mahsulotlar bo'limi</b>\n\nQanday amal bajaramiz?", reply_markup=products_menu_kb())

@router.message(F.text == "◀️ Orqaga", IsAdmin())
async def back_to_admin_menu(message: Message, state: FSMContext):
    await state.clear() 
    from handlers.admin import get_admin_menu
    await message.answer("Bosh menyuga qaytdik.", reply_markup=get_admin_menu())

# ==========================================
# 3. GLOBAL BEKOR QILISH 
# ==========================================
@router.message(Command("cancel"))
@router.message(F.text.lower() == "bekor qilish")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        return
    await state.clear()
    await message.answer("❌ Jarayon bekor qilindi.", reply_markup=products_menu_kb())

# ==========================================
# 4. RO'YXATNI KO'RISH
# ==========================================
@router.message(F.text == "📋 Mahsulotlar ro'yxati", IsAdmin())
async def list_products(message: Message, session: AsyncSession):
    result = await session.execute(select(Product).order_by(Product.name))
    products = result.scalars().all()

    if not products:
        await message.answer("📭 Omborda hozircha hech qanday mahsulot yo'q.")
        return

    text = "📋 <b>Ombordagi mahsulotlar:</b>\n\n"
    for p in products:
        text += f"▪️ <b>{p.name}</b> (Kod: <code>{p.code}</code>)\n"
        text += f"   Qoldiq: {p.quantity} ta | Narxi: {p.price:,.0f} so'm\n\n"
    
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x+4000])
    else:
        await message.answer(text)

# ==========================================
# 5. MAHSULOT O'CHIRISH (YANGI FUNKSIYA)
# ==========================================
@router.message(F.text == "🗑 Mahsulotni o'chirish", IsAdmin())
async def delete_product_start(message: Message, state: FSMContext):
    await message.answer(
        "🗑 O'chirmoqchi bo'lgan mahsulotingizning <b>kodini (artikul)</b> kiriting:\n\n"
        "<i>(Bekor qilish uchun /cancel deb yozing)</i>", 
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(DeleteProductForm.code)

@router.message(DeleteProductForm.code)
async def process_delete_product(message: Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip()
    
    result = await session.execute(select(Product).where(Product.code == code))
    product = result.scalar_one_or_none()
    
    if not product:
        await message.answer("⚠️ Bunday kodli mahsulot topilmadi. Qaytadan to'g'ri kod kiriting yoki /cancel bosing:")
        return

    try:
        product_name = product.name
        await session.delete(product)
        await session.commit()
        await message.answer(f"✅ <b>{product_name}</b> bazadan to'liq o'chirildi!", reply_markup=products_menu_kb())
        await state.clear()
        
    except IntegrityError:
        # Agar mahsulot oldin sotilgan bo'lsa, xatolik ushlanadi
        await session.rollback()
        await message.answer(
            "⚠️ <b>O'chirib bo'lmaydi!</b>\n\n"
            "Bu mahsulot oldin kimgadir sotilgan va xaridlar tarixida mavjud. "
            "Hisobotlar buzilmasligi uchun uni bazadan butunlay o'chirib bo'lmaydi.\n\n"
            "<i>(Maslahat: Shunchaki uning qoldig'ini 0 qilib qo'yishingiz mumkin)</i>",
            reply_markup=products_menu_kb()
        )
        await state.clear()
    except Exception as e:
        await session.rollback()
        logger.error(f"Mahsulotni o'chirishda xato: {e}")
        await message.answer("❌ Kutilmagan xatolik yuz berdi.", reply_markup=products_menu_kb())
        await state.clear()

# ==========================================
# 6. MAHSULOT QO'SHISH JARAYONI (FSM)
# ==========================================
@router.message(F.text == "➕ Yangi mahsulot qo'shish", IsAdmin())
async def add_product_start(message: Message, state: FSMContext):
    await message.answer("📝 Yangi mahsulot nomini kiriting:\n<i>(Bekor qilish uchun /cancel bosing)</i>", reply_markup=ReplyKeyboardRemove())
    await state.set_state(ProductForm.name)

@router.message(ProductForm.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("🔤 Endi mahsulot uchun maxsus <b>kod</b> (yoki artikul) kiriting:\n<i>Boshqa mahsulotlarnikiga o'xshamasligi kerak!</i>")
    await state.set_state(ProductForm.code)

@router.message(ProductForm.code)
async def process_code(message: Message, state: FSMContext, session: AsyncSession):
    code = message.text.strip()
    
    result = await session.execute(select(Product).where(Product.code == code))
    existing_product = result.scalar_one_or_none()
    
    if existing_product:
        await message.answer("⚠️ <b>Xatolik!</b> Bu kod bilan allaqachon mahsulot qo'shilgan. Iltimos, boshqa kod kiriting:")
        return 
        
    await state.update_data(code=code)
    await message.answer("🔢 Ombordagi <b>boshlang'ich soni</b>ni (butun raqamda) kiriting:")
    await state.set_state(ProductForm.quantity)

@router.message(ProductForm.quantity)
async def process_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting (masalan: 100):")
        return
        
    await state.update_data(quantity=int(message.text))
    await message.answer("💰 Mahsulotning <b>sotilish narxi</b>ni kiriting (so'mda):\n<i>Faqat raqam yozing, probel yoki vergullarsiz (masalan: 150000)</i>")
    await state.set_state(ProductForm.price)

@router.message(ProductForm.price)
async def process_price(message: Message, state: FSMContext, session: AsyncSession):
    try:
        price_val = float(message.text.replace(" ", ""))
    except ValueError:
        await message.answer("⚠️ Iltimos, narxni to'g'ri raqam shaklida kiriting:")
        return

    data = await state.get_data()
    
    new_product = Product(
        name=data['name'],
        code=data['code'],
        quantity=data['quantity'],
        price=price_val
    )
    
    try:
        session.add(new_product)
        await session.commit()
        
        await message.answer(
            f"✅ <b>Mahsulot muvaffaqiyatli qo'shildi!</b>\n\n"
            f"🏷 Nomi: {data['name']}\n"
            f"🔢 Kodi: {data['code']}\n"
            f"📦 Soni: {data['quantity']} ta\n"
            f"💰 Narxi: {price_val:,.0f} so'm",
            reply_markup=products_menu_kb()
        )
    except IntegrityError:
        await session.rollback()
        await message.answer("❌ Bazaga yozishda xatolik yuz berdi. Kod takrorlangan bo'lishi mumkin.", reply_markup=products_menu_kb())
    finally:
        await state.clear()