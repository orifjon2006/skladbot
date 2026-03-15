from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.models import Payment, Customer

# ==========================================
# 1. TO'LOV QABUL QILISH VA BALANSNI YANGILASH
# ==========================================
async def process_payment(session: AsyncSession, customer_id: int, amount: float, order_id: int = None) -> tuple[Payment, float]:
    """
    Mijozdan to'lov qabul qilish va uning balansini xavfsiz yangilash xizmati.
    Agar to'lov muayyan bitta xarid (order) uchun bo'lsa, order_id beriladi.
    Umumiy qarz uzish bo'lsa, order_id=None bo'ladi.
    """
    try:
        # 1. Mijozni bazadan olamiz
        customer = await session.get(Customer, customer_id)
        if not customer:
            raise ValueError("Mijoz topilmadi!")

        # 2. Balansni yangilaymiz (qarz kamayadi yoki haqdorlik oshadi)
        customer.balance += amount

        # 3. To'lov tarixini yozamiz
        new_payment = Payment(
            customer_id=customer.id,
            order_id=order_id,
            amount=amount
        )
        session.add(new_payment)

        # 4. Barchasini bitta tranzaksiyada saqlaymiz
        await session.commit()
        
        # Yangi to'lov obyekti va mijozning yangilangan balansini qaytaramiz
        return new_payment, customer.balance

    except Exception as e:
        # Xatolik yuz bersa, pul havoga uchib ketmasligi uchun orqaga qaytaramiz
        await session.rollback()
        raise e

# ==========================================
# 2. MIJOZNING TO'LOVLAR TARIXINI OLISH
# ==========================================
async def get_customer_payment_history(session: AsyncSession, customer_id: int, limit: int = 10) -> list[Payment]:
    """
    Mijozning oxirgi qilgan to'lovlari ro'yxatini olish.
    Standart holatda oxirgi 10 ta to'lovni ko'rsatadi.
    """
    result = await session.execute(
        select(Payment)
        .where(Payment.customer_id == customer_id)
        .order_by(Payment.created_at.desc()) # Eng yangilari birinchi chiqadi
        .limit(limit)
    )
    return list(result.scalars().all())

# ==========================================
# 3. KUNLIK TUSHUMNI HISOBLASH (HISOBOT UCHUN)
# ==========================================
async def get_total_payments_today(session: AsyncSession, start_of_day) -> float:
    """
    Bugungi kundagi jami tushumlarni (to'lovlarni) hisoblash.
    Hisobotlar bo'limi uchun ishlatiladi.
    """
    result = await session.execute(
        select(Payment)
        .where(Payment.created_at >= start_of_day)
    )
    payments = result.scalars().all()
    
    # Barcha to'lovlar summasini qo'shib chiqamiz
    total_amount = sum(p.amount for p in payments)
    return total_amount