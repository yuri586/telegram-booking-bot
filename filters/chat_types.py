from aiogram import types
from aiogram.filters import Filter

from config import settings


class ChatTypeFilter(Filter):
    def __init__(self, chat_types: list[str]):
        self.chat_types = chat_types

    async def __call__(self, message: types.Message) -> bool:
        return message.chat.type in self.chat_types


class IsAdmin(Filter):
    async def __call__(self, message: types.Message) -> bool:
        if not message.from_user:
            return False

        user_id = message.from_user.id

        # Приватная админка: только whitelist из ENV
        return user_id in settings.ADMIN_IDS

        
