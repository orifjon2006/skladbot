import logging
from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from database.models import Customer

# Xatoliklarni terminalda ko'rish uchun logger sozlaymiz
logger = logging.getLogger(__name__)

# ==========================================
# 1. XARID CHEKINI YUBORISH
# ==========================================
async def send_receipt(
    bot: Bot, 
    customer: Customer, 
    total_price: float, 
    paid_amount: float, 
    debt: float, 
    products_text: str,
    receipt_code: str = "Mavjud emas" # YANGI: 6 talik kod uchun parametr qo'shildi
) -> bool:
    """
    Mijozga xarid amalga oshirilganda avtomatik chek yuborish.
    Agar mijozning telegram_id si yo'q bo'lsa (botga kirmagan bo'lsa), xabar yuborilmaydi.
    """
    if not customer.telegram_id:
        logger.info(f"Mijoz {customer.name} tizimda telegram_id ga ega emas. Xabar yuborish bekor qilindi.")
        return False
        
    # Balansni chiroyli ko'rsatish
    if customer.balance < 0:
        balance_info = f"📉 <b>Sizning umumiy qarzingiz:</b> {abs(customer.balance):,.0f} so'm"
    elif customer.balance > 0:
        balance_info = f"📈 <b>Sizning haqingiz (ortiqcha to'lov):</b> {customer.balance:,.0f} so'm"
    else:
        balance_info = "⚖️ <b>Sizda qarz yo'q.</b>"
        
    text = (
        f"🧾 <b>Xarid cheki</b>\n"
        f"🔑 <b>Xarid kodi:</b> <code>{receipt_code}</code>\n\n" # YANGI: Kod chekda chiqadi
        f"📦 <b>Mahsulotlar:</b>\n{products_text}\n"
        f"💰 <b>Jami:</b> {total_price:,.0f} so'm\n"
        f"💵 <b>To'landi:</b> {paid_amount:,.0f} so'm\n"
        f"📉 <b>Bu xariddan qarz:</b> {debt:,.0f} so'm\n\n"
        f"💳 {balance_info}\n\n"
        f"<i>Xaridingiz uchun rahmat! Biz bilan qolganingizdan xursandmiz.</i>"
    )

    try:
        # Xabarni mijozning shaxsiy lichkasiga yuboramiz
        await bot.send_message(chat_id=customer.telegram_id, text=text)
        return True
    except TelegramAPIError as e:
        # Agar mijoz botni bloklab qo'ygan bo'lsa, tizim qotib qolmasligi uchun xatoni ushlab qolamiz
        logger.error(f"Xabar yuborishda xatolik (Mijoz: {customer.name}): {e}")
        return False


# ==========================================
# 2. TO'LOV QABUL QILINGANLIGI HAQIDA XABAR
# ==========================================
async def send_payment_notification(bot: Bot, customer: Customer, amount: float) -> bool:
    """
    Mijoz qarzini uzish uchun to'lov qilganda yuboriladigan tasdiq xabari.
    """
    if not customer.telegram_id:
        return False
        
    if customer.balance < 0:
        balance_info = f"📉 <b>Qolgan qarzingiz:</b> {abs(customer.balance):,.0f} so'm"
    elif customer.balance > 0:
        balance_info = f"📈 <b>Ortiqcha to'lov (haqdorlik):</b> {customer.balance:,.0f} so'm"
    else:
        balance_info = "🎉 <b>Barcha qarzlaringiz uzildi. Rahmat!</b>"
        
    text = (
        f"✅ <b>To'lov qabul qilindi!</b>\n\n"
        f"💵 <b>To'langan summa:</b> {amount:,.0f} so'm\n"
        f"💳 <b>Yangi holat:</b>\n{balance_info}\n\n"
        f"<i>To'lovingiz uchun rahmat!</i>"
    )

    try:
        await bot.send_message(chat_id=customer.telegram_id, text=text)
        return True
    except TelegramAPIError as e:
        logger.error(f"To'lov xabarini yuborishda xatolik (Mijoz: {customer.name}): {e}")
        return False