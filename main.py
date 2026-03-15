import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# Sozlamalar va baza
from config import BOT_TOKEN
from database.db import init_db, async_session_maker

# Xizmatlar (Scheduler va b.)
from services.scheduler_service import setup_scheduler

# Handlerlar (Routerlar)
from handlers import admin, products, orders, payments, customers, customers_client

# Middleware
from middlewares.database import DbSessionMiddleware

async def main() -> None:
    # 1. Loggingni sozlash
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        stream=sys.stdout
    )
    
    # 2. Ma'lumotlar bazasini initsializatsiya qilish
    await init_db()

    # 3. Bot va Dispatcher obyektlarini yaratish
    bot = Bot(
        token=BOT_TOKEN, 
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()

    # 4. MIDDLEWARE ulanishi (Barcha xabarlarga session yetkazish uchun)
    dp.update.middleware(DbSessionMiddleware(session_pool=async_session_maker))

    # 5. ROUTERLARNI ro'yxatdan o'tkazish
    # Tartib muhim: avval admin, keyin mijoz qismlari
    dp.include_router(admin.router)
    dp.include_router(products.router)
    dp.include_router(orders.router)
    dp.include_router(payments.router)
    dp.include_router(customers.router)
    dp.include_router(customers_client.router)

    # 6. SCHEDULERni ishga tushirish (Qarz eslatmalari uchun)
    setup_scheduler(bot, async_session_maker)

    try:
        # Eski xabarlarni tozalash va pollingni boshlash
        await bot.delete_webhook(drop_pending_updates=True) 
        print("🚀 bot muvaffaqiyatli ishga tushdi!")
        await dp.start_polling(bot)
    except Exception as e:
        logging.error(f"Bot ishlashida xatolik: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")