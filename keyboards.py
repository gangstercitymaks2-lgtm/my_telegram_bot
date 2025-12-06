from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from locations import ALL_LOCATIONS   # словарь всех водоёмов


def make_location_kb() -> InlineKeyboardMarkup:
    buttons, row = [], []
    for code, title in ALL_LOCATIONS.items():
        row.append(InlineKeyboardButton(title, callback_data=f"loc_{code}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)


# ---------- Шаг 2: выбор типа точки (до 2 значений + кнопка «Задание») ----------
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def make_point_type_kb(selected: list[str] | None = None) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора типа точки с возможностью выбирать несколько.
    selected — список уже выбранных ключей.
    """
    selected = selected or []

    items = [
        ("farm", "Фарм"),
        ("trof", "Трофей"),
        ("vys",  "Высед"),
        ("spot", "Задание"),
    ]

    rows = []
    for key, title in items:
        # ✅ зелёная галочка если пункт выбран
        label = f"{'✅ ' if key in selected else ''}{title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"pt_{key}")])

    rows.append([InlineKeyboardButton("➡️ Далее", callback_data="pt_next")])
    return InlineKeyboardMarkup(rows)



# --- Виды рыбы ---
def make_fish_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Разнорыбица 🐟", callback_data="fv_mix")],
        [InlineKeyboardButton("Написать самому ✍️", callback_data="fv_custom")]
    ])


# --- Тип ловли ---
def make_fishing_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Донка",    callback_data="ft_donka")],
        [InlineKeyboardButton("Поплавок", callback_data="ft_poplavok")],
        [InlineKeyboardButton("Спиннинг", callback_data="ft_spin")],
        [InlineKeyboardButton("Троллинг", callback_data="ft_trol")],
        [InlineKeyboardButton("Пилкинг",  callback_data="ft_pilk")],
    ])


def make_coordinates_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Троллинг", callback_data="coord_trol")],
        [InlineKeyboardButton("Написать координаты", callback_data="coord_custom")],
    ])


def make_temp_kb():
    """
    Клавиатура для выбора температуры с кнопкой 'Пропустить'.
    Возвращает InlineKeyboardMarkup с кнопками tmp_norm/tmp_high/tmp_low/tmp_skip.
    """
    keyboard = [
        [InlineKeyboardButton("Нормальная", callback_data="tmp_norm"),
         InlineKeyboardButton("Повышенная", callback_data="tmp_high")],
        [InlineKeyboardButton("Пониженная", callback_data="tmp_low")],
        # Кнопка пропустить в отдельном ряду
        [InlineKeyboardButton("⏭ Пропустить", callback_data="tmp_skip")]
    ]
    return InlineKeyboardMarkup(keyboard)


def make_photo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("📸 Загрузить", callback_data="photo_start")]])


def make_comment_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить", callback_data="comment_skip")]])


def make_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Опубликовать (на модерацию)", callback_data="confirm_publish")],
        [InlineKeyboardButton("❌ Отмена", callback_data="confirm_cancel")],
    ])


def make_moderation_kb(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👍 Одобрить", callback_data=f"mod_ok:{user_id}"),
            InlineKeyboardButton("🚫 Отклонить", callback_data=f"mod_no:{user_id}")
        ]
    ])
