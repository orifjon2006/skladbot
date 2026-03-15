from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database.models import Order, OrderItem, Product, Customer, Payment

# ==========================================
# 1. XARIDNI BAZAGA YOZISH (ASOSIY TRANZAKSIYA)
# ==========================================
async def create_order_transaction(
    session: AsyncSession, 
    customer_id: int, 
    cart: dict, 
    paid_amount: float
) -> tuple[Order, float]:
    """
    Savatdagi mahsulotlarni, to'lovni va mijoz qarzini yagona xavfsiz tranzaksiyada bazaga saqlash.
    cart strukturasi: {product_id: {'name': str, 'qty': int, 'price': float}}
    """
    try:
        # 1. Mijozni chaqirib olamiz
        customer = await session.get(Customer, customer_id)
        if not customer:
            raise ValueError("Mijoz topilmadi!")

        total_price = 0.0

        # 2. Buyurtma (Order) yaratamiz
        new_order = Order(customer_id=customer.id, status="delivered")
        session.add(new_order)
        await session.flush() # ID raqami shakllanishi uchun flush qilamiz

        # 3. Savatdagi har bir mahsulotni aylanib chiqamiz
        for prod_id, item_data in cart.items():
            qty = item_data['qty']
            price = item_data['price']
            
            # Ombordagi mahsulotni olib, qoldiqni tekshiramiz
            product = await session.get(Product, prod_id)
            if product.quantity < qty:
                raise ValueError(f"Xatolik: {product.name} omborda yetarli emas! Qoldiq: {product.quantity}")

            # Ombordan ayiramiz
            product.quantity -= qty
            
            # Jami summani hisoblaymiz
            item_total = price * qty
            total_price += item_total

            # OrderItem (Chek ichidagi qatorlar) yaratamiz
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=prod_id,
                quantity=qty,
                price=price
            )
            session.add(order_item)

        # Buyurtmaning umumiy summasini saqlaymiz
        new_order.total_price = total_price

        # 4. Qarzni hisoblash va Mijoz balansini yangilash
        debt = total_price - paid_amount
        customer.balance -= debt # Mijoz to'liq to'lamasa, balansi minusga (qarzga) qarab ketadi

        # 5. To'lovni qayd etish (agar pul bergan bo'lsa)
        if paid_amount > 0:
            payment = Payment(
                customer_id=customer.id, 
                order_id=new_order.id, 
                amount=paid_amount
            )
            session.add(payment)

        # 6. BARCHA O'ZGARISHLARNI BAZAGA MUHRLASH
        await session.commit()
        return new_order, debt

    except Exception as e:
        # Agar yuqoridagi qadamlarning birortasida xatolik chiqsa, hech qaysi o'zgarish bazaga yozilmaydi
        await session.rollback()
        raise e

# ==========================================
# 2. BUYURTMA STATUSINI O'ZGARTIRISH
# ==========================================
async def update_order_status(session: AsyncSession, order_id: int, new_status: str) -> bool:
    """Buyurtma holatini o'zgartirish (masalan: 'cancelled', 'confirmed')"""
    order = await session.get(Order, order_id)
    if not order:
        return False
        
    order.status = new_status
    await session.commit()
    return True

# ==========================================
# 3. MIJOZNING BARCHA BUYURTMALARINI OLISH
# ==========================================
async def get_customer_orders(session: AsyncSession, customer_id: int) -> list[Order]:
    """Muayyan mijozga tegishli barcha buyurtmalarni olish"""
    # selectinload orqali buyurtmaga tegishli mahsulotlar ro'yxatini ham qo'shib tortib olamiz (N+1 muammosini oldini oladi)
    result = await session.execute(
        select(Order)
        .where(Order.customer_id == customer_id)
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    return list(result.scalars().all())