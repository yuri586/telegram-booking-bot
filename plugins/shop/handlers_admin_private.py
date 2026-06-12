from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from database.orm_query import (
    orm_add_product,
    orm_delete_product,
    orm_get_product,
    orm_get_products,
    orm_update_product,
)
from filters.chat_types import ChatTypeFilter, IsAdmin
from keyboards.admin_reply import ADMIN_KB
from keyboards.inline import get_inline_buttons
from keyboards.reply import get_keyboard

logger = logging.getLogger(__name__)

admin_router = Router()
admin_router.message.filter(ChatTypeFilter(["private"]), IsAdmin())

# ---------------- Тексты / подсказки ----------------

EDIT_RULES_TEXT = ("\n✏️  . / назад / отмена")



# ---------------- Shop-клавиатура (плагин товаров) ----------------

SHOP_KB = get_keyboard(
    "Добавить товар",
    "Ассортимент",
    "⬅️ Назад в админ-меню",
    placeholder="Товары: выберите действие",
    sizes=(2, 1),
)

async def _open_shop_menu(message: types.Message) -> None:
    await message.answer("🛒 Товары: что хотите сделать?", reply_markup=SHOP_KB)




class AddProduct(StatesGroup):
    title = State()
    description = State()
    price = State()
    photo = State()

    texts = {
        "AddProduct:title": "Введите название товара:",
        "AddProduct:description": "Введите описание товара:",
        "AddProduct:price": "Введите стоимость товара:",
        "AddProduct:photo": "Отправьте фото товара:",
    }




@admin_router.message(Command("shop"))
@admin_router.message(F.text == "Товары")
async def shop_menu(message: types.Message):
    await _open_shop_menu(message)

@admin_router.message(F.text == "⬅️ Назад в админ-меню")
async def back_to_admin_menu(message: types.Message):
    await message.answer("Админ-меню:", reply_markup=ADMIN_KB)


# ---------------- Просмотр ассортимента ----------------

@admin_router.message(F.text == "Ассортимент")
async def show_products(message: types.Message, session: AsyncSession):
    products = await orm_get_products(session)

    if not products:
        await message.answer("Товаров пока нет.", reply_markup=SHOP_KB)
        return

    for product in products:
        price_text = f"{Decimal(str(product.price)):.2f}"

        caption = (
            f"<strong>{product.title}</strong>\n"
            f"{product.description or ''}\n"
            f"Стоимость: {price_text}"
        )

        markup = get_inline_buttons(
            btns={
                "Редактировать": f"edit_{product.id}",
                "Удалить": f"delete_{product.id}",
            },
        )

        if product.photo:
            await message.answer_photo(
                photo=product.photo,
                caption=caption,
                reply_markup=markup,
            )
        else:
            await message.answer(caption, reply_markup=markup)

    await message.answer("Вот список товаров ⏫", reply_markup=SHOP_KB)


# ---------------- Удаление товара ----------------

@admin_router.callback_query(F.data.startswith("delete_"))
async def delete_product_callback(callback: types.CallbackQuery, session: AsyncSession):
    if not callback.data:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    try:
        product_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    await orm_delete_product(session, product_id)
    await callback.answer("Товар удалён ✅")

    if isinstance(callback.message, Message):
        # Если карточка была фото — редактируем подпись, иначе текст
        if callback.message.photo:
            await callback.message.edit_caption("✅ Товар удалён", reply_markup=None)
        else:
            await callback.message.edit_text("✅ Товар удалён", reply_markup=None)


# ---------------- Редактирование товара (старт через callback) ----------------

@admin_router.callback_query(StateFilter(None), F.data.startswith("edit_"))
async def edit_product_callback(
    callback: types.CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
):
    if not callback.data:
        await callback.answer("Ошибка данных", show_alert=True)
        return

    try:
        product_id = int(callback.data.split("_")[-1])
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    product = await orm_get_product(session, product_id)
    if not product:
        await callback.answer("Товар не найден", show_alert=True)
        return

    # Сохраняем режим редактирования + старые значения (для ".")
    await state.set_data(
        {
            "edit_id": product.id,
            "old_title": product.title or "",
            "old_description": product.description or "",
            "old_price": str(product.price),
            "old_photo": product.photo or "",
        }
    )

    await callback.answer()

    if callback.message is None:
        return  # или логни

    await callback.message.answer(
        "Введите новое название товара.\n" + EDIT_RULES_TEXT,
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(AddProduct.title)


# ---------------- FSM: Добавление/Редактирование товара ----------------

# --- Старт FSM (добавление) ---
@admin_router.message(StateFilter(None), F.text == "Добавить товар")
async def add_product_start(message: types.Message, state: FSMContext):
    # На всякий: очищаем старый мусор (если вдруг)
    await state.clear()
    await message.answer(
        "Введите название товара:",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(AddProduct.title)


# --- Отмена ---
@admin_router.message(StateFilter("*"), Command("отмена"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        return

    await state.clear()
    await message.answer("Действия отменены", reply_markup=SHOP_KB)


# --- Назад ---
@admin_router.message(StateFilter("*"), Command("назад"))
@admin_router.message(StateFilter("*"), F.text.casefold() == "назад")
async def back_step_handler(message: types.Message, state: FSMContext):
    current = await state.get_state()

    if current is None:
        await message.answer("Нет активного действия. Напишите /admin.")
        return

    if current == AddProduct.title.state:
        await message.answer('Предыдущего шага нет. Введите название или напишите "отмена".')
        return

    previous = None
    steps = [AddProduct.title, AddProduct.description, AddProduct.price, AddProduct.photo]
    for step in steps:
        if step.state == current:
            if previous is None or previous.state is None:
                await message.answer('Предыдущего шага нет. Напишите "отмена".')
                return

            await state.set_state(previous)
            hint = AddProduct.texts.get(previous.state, "Введите значение:")
            await message.answer(f"Ок, вернулись назад.\n{hint}")
            return
        previous = step


# ---------------- Шаги FSM ----------------

# --- TITLE ---
@admin_router.message(AddProduct.title, F.text)
async def add_title(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()

    # "." работает только в режиме редактирования
    if text == "." and data.get("edit_id"):
        text = data.get("old_title", "")

    if not text:
        await message.answer("Название не может быть пустым.")
        return

    if len(text) > 100:
        await message.answer("Название не должно превышать 100 символов.")
        return

    await state.update_data(title=text)
    data = await state.get_data()
    await message.answer("Введите описание товара:")
    await state.set_state(AddProduct.description)


@admin_router.message(AddProduct.title)
async def add_title_invalid(message: types.Message):
    await message.answer("Введите текстовое название товара.")


# --- DESCRIPTION ---
@admin_router.message(AddProduct.description, F.text)
async def add_description(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()

    if text == "." and data.get("edit_id"):
        text = data.get("old_description", "")

    await state.update_data(description=text)
    data = await state.get_data()
    await message.answer("Введите стоимость товара:")
    await state.set_state(AddProduct.price)


@admin_router.message(AddProduct.description)
async def add_description_invalid(message: types.Message):
    await message.answer("Введите текстовое описание товара.")


# --- PRICE ---
@admin_router.message(AddProduct.price, F.text)
async def add_price(message: types.Message, state: FSMContext):
    text = (message.text or "").strip()
    data = await state.get_data()

    if text == "." and data.get("edit_id"):
        raw = str(data.get("old_price", "0")).replace(",", ".").strip()
    else:
        raw = text.replace(",", ".").strip()

    try:
        price = Decimal(raw)
    except InvalidOperation:
        await message.answer("Введите корректное число. Пример: 1999 или 1999.50")
        return

    # Храним строкой — дружит с ORM и сериализацией
    await state.update_data(price=str(price))
    data = await state.get_data()
    await message.answer("Отправьте фото товара:")
    await state.set_state(AddProduct.photo)


@admin_router.message(AddProduct.price)
async def add_price_invalid(message: types.Message):
    await message.answer("Введите стоимость числом:")


# --- PHOTO (финал): фото или "." ---
# --- PHOTO (финал) ---

async def _save_product(
    message: types.Message,
    state: FSMContext,
    session: AsyncSession,
    photo: str,
) -> None:
    data = await state.get_data()
    edit_id = data.get("edit_id")

    payload = {
        "title": data.get("title"),
        "description": data.get("description"),
        "price": data.get("price"),
        "photo": photo,
    }

    try:
        if edit_id:
            await orm_update_product(session, int(edit_id), payload)
            await message.answer("✅ Товар успешно обновлён.", reply_markup=SHOP_KB)
        else:
            title_raw = payload.get("title")
            description_raw = payload.get("description")
            price_raw = payload.get("price")
            photo_raw = payload.get("photo")

            if not isinstance(title_raw, str) or not title_raw.strip():
                await message.answer("Ошибка: отсутствует корректный title.", reply_markup=SHOP_KB)
                return

            if price_raw is None:
                await message.answer("Ошибка: отсутствует price.", reply_markup=SHOP_KB)
                return

            title: str = title_raw
            description: str | None = description_raw if isinstance(description_raw, str) else None
            photo_value: str | None = photo_raw if isinstance(photo_raw, str) else None
            price = price_raw

            await orm_add_product(
                session,
                title=title,
                description=description,
                price=price,
                photo=photo_value,
            )
            await message.answer("✅ Товар успешно добавлен.", reply_markup=SHOP_KB)

    except Exception:
        logger.exception("Ошибка при сохранении товара. payload=%s", payload)
        await message.answer("Ошибка при сохранении товара. Попробуйте позже.", reply_markup=SHOP_KB)
    finally:
        await state.clear()


# 1) Пришло фото
@admin_router.message(AddProduct.photo, F.photo)
async def finish_product_photo(message: types.Message, state: FSMContext, session: AsyncSession):
    if not message.photo:
        await message.answer('Нужно отправить фото. ("назад" / "отмена")')
        return

    photo = message.photo[-1].file_id
    await _save_product(message, state, session, photo)


# 2) Пришла точка — оставить старое фото (только редактирование)
@admin_router.message(AddProduct.photo, F.text == ".")
async def finish_product_dot(message: types.Message, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    edit_id = data.get("edit_id")

    if not edit_id:
        await message.answer("При добавлении нужно фото файлом. Отправьте фото.")
        return

    old_photo = data.get("old_photo", "")
    if not old_photo:
        await message.answer("Старого фото нет — отправьте фото файлом.")
        return

    await _save_product(message, state, session, old_photo)


# 3) Всё остальное — ошибка ввода
@admin_router.message(AddProduct.photo)
async def finish_product_invalid(message: types.Message):
    await message.answer('Нужно отправить фото или "." ("назад" / "отмена")')
