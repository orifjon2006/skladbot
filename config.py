import os
from dotenv import load_dotenv

# .env faylidagi ma'lumotlarni yuklab olish
load_dotenv()

# Bot tokenini olish
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("XATOLIK: BOT_TOKEN topilmadi! .env faylini tekshiring.")

# Ma'lumotlar bazasiga ulanish URL manzili
# Agar .env faylida DB_URL berilmagan bo'lsa, standart sifatida SQLite ishlatiladi
DB_URL = os.getenv("DB_URL", "sqlite+aiosqlite:///sklad_bot.db")

# Adminlarning Telegram ID larini olish (vergul bilan ajratilgan holda yoziladi)
# Masalan: ADMIN_IDS=123456789,987654321
admin_ids_str = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(admin_id.strip()) for admin_id in admin_ids_str.split(",") if admin_id.strip().isdigit()]

# Loyiha sozlamalari (Ixtiyoriy kengaytirish uchun)
TIMEZONE = "Asia/Tashkent"