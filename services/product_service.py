from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError

from database.models import Product

# ==========================================
# 1. MAHSULOT QO'SHISH (CREATE)
# ==========================================
async def create_product(session: AsyncSession, name: str, code: str, quantity: int, price: float) -> Product | str:
    """Yangi mahsulotni bazaga qo'shish xizmati"""
    new_product = Product(name=name, code=code, quantity=quantity, price=price)
    
    try:
        session.add(new_product)
        await session.commit()
        return new_product
    except IntegrityError:
        # Agar kod takrorlansa (bazada oldin bo'lsa), xatolikni ushlab qolamiz
        await session.rollback()
        return "duplicate_code"

# ==========================================
# 2. BARCHA MAHSULOTLARNI OLISH (READ)
# ==========================================
async def get_all_products(session: AsyncSession) -> list[Product]:
    """Ombordagi barcha mahsulotlarni alifbo tartibida olish"""
    result = await session.execute(select(Product).order_by(Product.name))
    return list(result.scalars().all())

# ==========================================
# 3. KOD ORQALI QIDIRISH (SEARCH)
# ==========================================
async def get_product_by_code(session: AsyncSession, code: str) -> Product | None:
    """Mahsulotni maxsus kodi bo'yicha topish"""
    result = await session.execute(select(Product).where(Product.code == code))
    return result.scalar_one_or_none()

# ==========================================
# 4. ID ORQALI OLISH VA QOLDIQNI TEKSHIRISH
# ==========================================
async def get_product_by_id(session: AsyncSession, product_id: int) -> Product | None:
    """Mahsulotni bazadagi ID raqami bo'yicha olish"""
    return await session.get(Product, product_id)

# ==========================================
# 5. QOLDIQNI YANGILASH (UPDATE)
# ==========================================
async def update_product_quantity(session: AsyncSession, product_id: int, quantity_change: int) -> bool:
    """
    Mahsulot sonini o'zgartirish. 
    Sotilganda manfiy (-5), omborga keltirilganda musbat (+10) raqam beriladi.
    """
    product = await session.get(Product, product_id)
    if not product:
        return False
        
    # Qoldiq noldan tushib ketmasligini tekshirish
    if product.quantity + quantity_change < 0:
         return False
         
    product.quantity += quantity_change
    await session.commit()
    return True

# ==========================================
# 6. MAHSULOTNI O'CHIRISH (DELETE)
# ==========================================
async def delete_product(session: AsyncSession, product_id: int) -> bool:
    """Mahsulotni bazadan o'chirish (agar u hali sotilmagan bo'lsa)"""
    product = await session.get(Product, product_id)
    if not product:
        return False
        
    try:
        await session.delete(product)
        await session.commit()
        return True
    except IntegrityError:
        # Agar bu mahsulot allaqachon order_items da ishtirok etgan bo'lsa (sotilgan bo'lsa),
        # RESTRICT qoidasi ishlaydi va o'chirishga ruxsat bermaydi. Tarixni buzmaslik uchun.
        await session.rollback()
        return False