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

# ==========================================
# 1. SAVDO FSM HOLATLARI
# ==========================================
class OrderForm(StatesGroup):
    customer_phone = State()  # Mijoz raqami
    product_code = State()    # Mahsulot kodi
    quantity = State()        # Olinayotgan soni
    cart_action = State()     # Savat menyusi (yana qo'shish yoki to'lov)
    payment = State()         # To'lanayotgan summa

# ==========================================
# 2. KLAVIATURALAR
# ==========================================
def cart_menu_kb() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="➕ Yana mahsulot qo'shish")],
        [KeyboardButton(text="💳 To'lovga o'tish"), KeyboardButton(text="❌ Xaridni bekor qilish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ==========================================
# 3. GLOBAL BEKOR QILISH
# ==========================================
@router.message(Command("cancel"))
@router.message(F.text == "❌ Xaridni bekor qilish")
async def cancel_order_process(message: Message, state: FSMContext):
    await state.clear()
    from handlers.admin import get_admin_menu
    await message.answer("🗑 Xarid jarayoni bekor qilindi. Savat xotiradan tozalandi.", reply_markup=get_admin_menu())

# ==========================================
# 4. SAVDONI BOSHLASH
# ==========================================
@router.message(F.text == "🛒 Savdo bo'limi", IsAdmin())
async def start_order(message: Message, state: FSMContext):
    await state.clear()
    # Savatni va jami summani FSM ichida initsializatsiya qilamiz
    await state.update_data(cart={}, total_sum=0) 
    
    await message.answer(
        "🛒 <b>Yangi xarid rasmiylashtirish:</b>\n\n"
        "Mijozning telefon raqamini kiriting (masalan: 998901234567):\n"
        "<i>(Noma'lum mijoz uchun 0 ni bosing)</i>",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(OrderForm.customer_phone)

# ==========================================
# 5. MIJOZNI ANIQLASH YOKI YARATISH
# ==========================================
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
    
    # Yangi mijoz bo'lsa darhol bazaga yozamiz (ID olish uchun)
    if not customer:
        customer = Customer(name=customer_name, phone=phone)
        session.add(customer)
        await session.commit() 
        await session.refresh(customer) # Bazadagi yangi ID ni yuklab olamiz
        
    await state.update_data(customer_id=customer.id)
    await message.answer(f"👤 Mijoz: <b>{customer.name}</b>\n\n🔍 Sotiladigan <b>mahsulot kodini</b> kiriting:")
    await state.set_state(OrderForm.product_code)

# ==========================================
# 6. MAHSULOTNI QIDIRISH
# ==========================================
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

# ==========================================
# 7. SAVATGA QO'SHISH 
# ==========================================
@router.message(OrderForm.quantity)
async def process_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Faqat raqam kiriting:")
        return
        
    qty = int(message.text)
    data = await state.get_data()
    
    if qty <= 0 or qty > data['max_qty']:
        await message.answer(f"⚠️ Xato! 1 dan {data['max_qty']} gacha raqam kiriting:")
        return
        
    cart = data.get('cart', {})
    prod_id = data['current_product_id']
    
    # Savatda bo'lsa qo'shamiz, bo'lmasa yangi qator
    if str(prod_id) in cart:
        cart[str(prod_id)]['qty'] += qty
    else:
        cart[str(prod_id)] = {
            'id': prod_id,
            'name': data['current_product_name'],
            'price': data['current_price'],
            'qty': qty
        }
        
    total_sum = sum(item['price'] * item['qty'] for item in cart.values())
    await state.update_data(cart=cart, total_sum=total_sum)
    
    # Savat ko'rinishi
    cart_msg = "🛒 <b>Savat tarkibi:</b>\n\n"
    for item in cart.values():
        cart_msg += f"▪️ {item['name']} x {item['qty']} = {item['price']*item['qty']:,.0f} so'm\n"
    cart_msg += f"\n💵 <b>Jami: {total_sum:,.0f} so'm</b>"
    
    await message.answer(cart_msg, reply_markup=cart_menu_kb())
    await state.set_state(OrderForm.cart_action)

# ==========================================
# 8. SAVAT BOSHQARUVI
# ==========================================
@router.message(OrderForm.cart_action, F.text == "➕ Yana mahsulot qo'shish")
async def add_more(message: Message, state: FSMContext):
    await message.answer("🔍 Mahsulot kodini kiriting:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderForm.product_code)

@router.message(OrderForm.cart_action, F.text == "💳 To'lovga o'tish")
async def go_pay(message: Message, state: FSMContext):
    data = await state.get_data()
    total = data.get('total_sum', 0)
    await message.answer(
        f"💵 Jami: <b>{total:,.0f} so'm</b>\n\n"
        f"Mijoz to'lagan summa (faqat raqam):", 
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(OrderForm.payment)

# ==========================================
# 9. FINAL: TRANZAKSIYA VA XABARNOMALAR
# ==========================================
@router.message(OrderForm.payment)
async def finalize_order(message: Message, state: FSMContext, session: AsyncSession):
    try:
        val = message.text.replace(" ", "").replace(",", "")
        paid_amount = float(val)
    except ValueError:
        await message.answer("⚠️ Faqat raqam kiriting (masalan: 50000):")
        return
        
    data = await state.get_data()
    cart = data.get('cart', {})
    total_sum = data.get('total_sum', 0)
    customer_id = data.get('customer_id')
    
    try:
        # 1. Mijoz balansini yangilash
        customer = await session.get(Customer, customer_id)
        debt = total_sum - paid_amount
        customer.balance -= debt 
        
        # 2. Tasodifiy 6 talik kod yaratish (Faqat katta harf va raqamlar)
        generated_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        # 3. Buyurtma yaratish (receipt_code bilan)
        new_order = Order(
            customer_id=customer.id, 
            total_price=total_sum, 
            status="delivered",
            receipt_code=generated_code
        )
        session.add(new_order)
        await session.flush()
        
        # 4. Mahsulotlar va Omborni yangilash
        receipt_text = ""
        for item in cart.values():
            product = await session.get(Product, item['id'])
            if product.quantity < item['qty']:
                 raise Exception(f"{product.name} yetarli emas!")
            
            product.quantity -= item['qty']
            
            order_item = OrderItem(
                order_id=new_order.id, 
                product_id=product.id, 
                quantity=item['qty'], 
                price=item['price']
            )
            session.add(order_item)
            receipt_text += f"- {item['name']} x {item['qty']} ta\n"
            
        # 5. To'lov tarixi
        if paid_amount > 0:
            payment = Payment(customer_id=customer.id, order_id=new_order.id, amount=paid_amount)
            session.add(payment)
            
        # 6. Barchasini bitta commit bilan saqlaymiz
        await session.commit()
        
        # 7. ADMINGA JAVOB
        final_text = (
            f"✅ <b>Xarid yakunlandi!</b>\n\n"
            f"🔑 <b>MIJOZ UCHUN KOD:</b> <code>{generated_code}</code>\n\n"
            f"💰 Jami: {total_sum:,.0f} so'm\n"
            f"💵 To'landi: {paid_amount:,.0f} so'm\n"
            f"📉 Qarz: {debt:,.0f} so'm\n"
            f"💳 Mijoz balansi: {customer.balance:,.0f} so'm"
        )
        
        from handlers.admin import get_admin_menu
        await message.answer(final_text, reply_markup=get_admin_menu())
        
        # 8. MIJOZGA AVTO-XABAR (NOTIFICATION) - YANGILANGAN QISM
        await send_receipt(
            bot=message.bot, 
            customer=customer, 
            total_price=total_sum, 
            paid_amount=paid_amount, 
            debt=debt, 
            products_text=receipt_text,
            receipt_code=generated_code # KOD MIJOZGA YUBORILADI
        )
        
        await state.clear()

    except Exception as e:
        await session.rollback()
        logger.error(f"Xaridda xatolik: {e}")
        await message.answer(f"❌ Xatolik yuz berdi: {str(e)}")
        await state.clear()