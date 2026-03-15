from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Har bir xabar uchun bazaga yangi, xavfsiz ulanish (session) ochamiz
        async with self.session_pool() as session:
            # Sessiyani handlerlarga (data lug'ati orqali) uzatamiz
            data["session"] = session
            
            # Handler o'z ishini bajarishini kutamiz
            result = await handler(event, data)
            
            # async with bloki tugagach, sessiya avtomatik va xavfsiz yopiladi
            return result