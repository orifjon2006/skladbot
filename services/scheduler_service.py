import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy import select
from aiogram import Bot

from database.models import Customer

async def send_debt_reminders(bot: Bot, session_pool: async_sessionmaker):
    """Bazada qarzi bor va telegram_id si mavjud barcha mijozlarga eslatma yuborish"""
    async with session_pool() as session:
        # Balansi 0 dan kichik va Telegram ID si bor mijozlarni qidiramiz
        result = await session.execute(
            select(Customer).where(Customer.balance < 0, Customer.telegram_id.isnot(None))
        )
        debtors = result.scalars().all()
        
        for debtor in debtors:
            text = (
                f"❗️ <b>Qarzdorlik eslatmasi</b>\n\n"
                f"Hurmatli <b>{debtor.name}</b>, sizning do'konimizdan joriy qarzdorligingiz: <b>{abs(debtor.balance):,.0f} so'm</b>.\n\n"
                f"<i>Iltimos, imkon qadar tezroq to'lovni amalga oshiring. Hamkorligingiz uchun rahmat!</i>"
            )
            try:
                await bot.send_message(chat_id=debtor.telegram_id, text=text)
            except Exception as e:
                logging.error(f"Eslatma yuborishda xatolik ({debtor.name}): {e}")

def setup_scheduler(bot: Bot, session_pool: async_sessionmaker) -> AsyncIOScheduler:
    """Taymerni sozlash va ishga tushirish"""
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    
    # Har 3 kunda bir marta, ertalab soat 10:00 da ishga tushadigan qilib belgilaymiz
    scheduler.add_job(
        send_debt_reminders, 
        trigger='interval', 
        days=3, # Har 3 kun
        start_date='2024-01-01 10:00:00', # Ertalab soat 10 da boshlanishini ta'minlash uchun xronologiya
        args=[bot, session_pool]
    )
    
    scheduler.start()
    return scheduler