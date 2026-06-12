
#pprint(event.model_dump(), width=120)

from pprint import pprint

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

from config import settings


class DebugUpdateMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data):
        if not isinstance(event, Update):
            return await handler(event, data)

        update = event

        msg = (
            update.message
            or update.edited_message
            or update.channel_post
            or update.edited_channel_post
        )

        
        # если дебаг выключен — ничего не печатаем
        if not settings.DEBUG or not settings.DEBUG_INCOMING:
            return await handler(event, data) 

        # FULL DUMP режим: печатаем и выходим (без краткого лога)
        if settings.DEBUG_UPDATES_FULL:
            print("\n" + "=" * 50)
            print(f"FULL UPDATE DUMP | ID: {event.update_id}")
            pprint(event.model_dump(exclude_none=True), width=120)
            print("=" * 50)
            return await handler(event, data)





        def header():
            print("\n" + "=" * 50)
            print(f"UPDATE ID: {event.update_id}")

        def footer():
            print("=" * 50)

        # 1) Сообщения (включая редактированные и посты)
        msg = event.message or event.edited_message or event.channel_post or event.edited_channel_post
        if msg:
            header()
            print(f"CHAT: {msg.chat.type} | chat_id={msg.chat.id}")

            sender_chat = getattr(msg, "sender_chat", None)

            if msg.from_user:
                u = msg.from_user
                uname = f"@{u.username}" if u.username else "(no username)"
                print(f"FROM: user_id={u.id} {uname} | is_bot={u.is_bot}")

            elif sender_chat is not None:
                print(f"FROM: sender_chat_id={sender_chat.id} | title={sender_chat.title!r}")
            else:
                print("FROM: <none>")


            content = msg.text if msg.text is not None else msg.caption
            print(f"CONTENT: {content!r}")

            # кратко про тип контента
            kind = []
            if msg.photo: 
                kind.append("photo")
            if msg.video: 
                kind.append("video")
            if msg.document: 
                kind.append("document")
            if msg.voice: 
                kind.append("voice")
            if msg.sticker: 
                kind.append("sticker")
            if kind:
                print(f"KIND: {', '.join(kind)}")

            footer()
            return await handler(event, data)

        # 2) Инлайн-кнопки
        cq = event.callback_query
        if cq:
            header()
            print(f"CALLBACK FROM: user_id={cq.from_user.id} @{cq.from_user.username}")
            print(f"DATA: {cq.data!r}")
            footer()
            return await handler(event, data)

        # 3) Остальное — хотя бы тип апдейта
        # чтобы видеть, что прилетает, даже если не обработал
        header()
        print(f"UPDATE KEYS: {[k for k, v in event.model_dump(exclude_none=True).items() if v is not None]}")
        footer()

        return await handler(event, data)


   
    