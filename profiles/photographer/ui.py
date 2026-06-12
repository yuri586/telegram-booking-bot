from profiles.common_labels import BASE_LABELS, BOOKING_LABELS
from profiles.ui_contract import ProfileUI

PHOTO_LABELS = BASE_LABELS | BOOKING_LABELS | {
    "about": "ℹ️ О фотографе",
    "help": "❓ Как записаться",
}

ui = ProfileUI(
    labels=PHOTO_LABELS,
    messages={
        "welcome": "Здравствуйте. Выберите, с чего хотите начать: посмотреть форматы съёмки, условия работы или записаться.",
        "sections_title": "📚 Разделы:",
        "page_not_found": "Страница не найдена",
        "section_missing": "Не выбран раздел.",
        "section_empty": "В разделе «{section_title}» пока нет материалов.",
        "item_or_section_missing": "Нет данных item/section",
        "item_not_found": "Элемент не найден",
    },
    titles={
        "main": "📸 Фотограф",
    },
)