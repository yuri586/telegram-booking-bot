# Модерация контента ботом в группах.
from string import punctuation

from aiogram import Bot, F, Router, types
from aiogram.filters import Command

from filters.chat_types import ChatTypeFilter

user_group_router = Router()
user_group_router.message.filter(ChatTypeFilter(chat_types=["group", "supergroup"]))
user_group_router.edited_message.filter(ChatTypeFilter(["group", "supergroup"]))

restricted_words = {"кабан", "хомяк", "выхухоль", "крыса", "мышь"}

def clean_text(text: str):
    return text.translate(str.maketrans("", "", punctuation))


@user_group_router.message(Command("admin"))
async def update_admins(message: types.Message, bot: Bot):
    admins = await bot.get_chat_administrators(message.chat.id)
    #просмотреть все данные и свойства полученых объектов админов
   

    # Собираем ID админов группы
    admin_ids = {
        m.user.id
        for m in admins
        if m.status in ("creator", "administrator")
    }

    # 1) Проверяем: отправитель сам админ?
    sender_id = message.from_user.id if message.from_user else None
    if sender_id not in admin_ids:
        # Мягко игнорируем (чтобы не палить механику и не засорять чат)
        # Можно вместо return отправить короткий ответ и удалить через 3 сек — но пока проще так.
        return

    

    # 3) Чистим команду из чата (если есть права)
    try:
        await message.delete()
    except Exception:
        pass



@user_group_router.edited_message(F.text)
@user_group_router.message(F.text)
async def cleaner(message: types.Message):
    text = message.text
    if not text:
        return
    
    cleaned = clean_text(text.lower())

    if restricted_words.intersection(cleaned.split()):
        user = message.from_user
        name = (
            (user.first_name if user else None)
            or (user.full_name if user else None)
            or "кто-то"
        )

        await message.answer(f"{name}, соблюдайте порядок в чате!")
        await message.delete()