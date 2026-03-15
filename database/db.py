from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from database.models import Base
from config import DB_URL

# 1. Asinxron dvigatelni (engine) yaratish
# pool_pre_ping=True parametri ulanish uzilib qolmasligini nazorat qiladi
engine = create_async_engine(
    url=DB_URL,
    echo=False,  # Konsolga barcha SQL so'rovlarni chiqarishni o'chiramiz (tezlik uchun)
    pool_pre_ping=True 
)

# 2. Sessiya yaratuvchi fabrika (SessionMaker)
# Bu orqali biz bazaga ma'lumot qo'shamiz yoki o'qiymiz
async_session_maker = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False, # Sessiya yopilgandan keyin ham obyektlardan foydalanish imkonini beradi
    autoflush=False
)

# 3. Jadvallarni yaratish funksiyasi (main.py da ishga tushiriladi)
async def init_db() -> None:
    async with engine.begin() as conn:
        # Barcha modellarni bazaga yozish (agar mavjud bo'lmasa yaratadi)
        # DIQQAT: Agar jadvallarni o'zgartirsangiz, alembic (migratsiya) ishlatish tavsiya etiladi
        await conn.run_sync(Base.metadata.create_all)

# 4. Ulanishni xavfsiz yopish funksiyasi
async def close_db() -> None:
    await engine.dispose()