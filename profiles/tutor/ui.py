from profiles.common_labels import BASE_LABELS, BOOKING_LABELS
from profiles.ui_contract import ProfileUI

TUTOR_LABELS = BASE_LABELS | BOOKING_LABELS | {
    "about": "ℹ️ О преподавателе",
    "help": "❓ Как записаться",
}

ui = ProfileUI(
    labels=TUTOR_LABELS,
    messages={
        "welcome": "Здравствуйте. Выберите раздел или сразу запишитесь на занятие.",
        "sections_title": "📚 Полезная информация:",
        "page_not_found": "Страница не найдена.",
        "section_missing": "Не выбран раздел.",
        "section_empty": "В разделе «{section_title}» пока нет материалов.",
        "item_or_section_missing": "Не хватает данных для открытия материала.",
        "item_not_found": "Материал не найден.",
    },
    titles={
        "main": "📘 Репетитор по математике",
    },
)