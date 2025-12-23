import logging
import json
import os
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from keyboards import (
    make_location_kb, make_point_type_kb, make_fish_type_kb,
    make_fishing_type_kb, make_coordinates_kb, make_temp_kb,
    make_confirm_kb, make_moderation_kb
)

from database import save_draft, load_draft, delete_draft

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# --- Словарь водоёмов ---
location_map = {
    "oz_komarino": "оз. Комариное",
    "oz_losinoe": "оз. Лосиное",
    "r_vyunok": "р. Вьюнок",
    "oz_stary_ostrog": "оз. Старый Острог",
    "r_belaya": "р. Белая",
    "oz_kuori": "оз. Куори",
    "oz_medvezhye": "оз. Медвежье",
    "r_volhov": "р. Волхов",
    "r_severskiy_donets": "р. Северский Донец",
    "r_sura": "р. Сура",
    "ladoga": "Ладожское озеро",
    "oz_yantarnoe": "оз. Янтарное",
    "ladoga_arch": "Ладожский архипелаг",
    "r_ahtuba": "р. Ахтуба",
    "oz_mednoe": "оз. Медное",
    "r_nizhnyaya_tunguska": "р. Нижняя Тунгуска",
    "r_yama": "р. Яма",
    "norwegian_sea": "Норвежское море",
    "penalty_pond": "Штрафной пруд",
}

(
    GREETING, LOCATION, POINT_TYPE, FISH_TYPE, FISH_TYPE_TEXT,
 FISHING_TYPE, DETAIL, COORDS, COORDS_TEXT,
 TEMP, PHOTOS, COMMENT, COMMENT_TEXT, AUTHOR, PREVIEW) = range(15)


def _mod_chat_id():
    v = os.getenv("MOD_CHAT_ID") or os.getenv("MODERATORS_CHAT_ID")
    return int(v) if v else None


# ----------------- Утилиты навигации -----------------
def nav_kb_row(back: str | None = None, nxt: str | None = None):
    """Возвращает строку кнопок навигации (неполная клавиатура)."""
    row = []
    if back:
        row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"go_back:{back}"))
    if nxt:
        row.append(InlineKeyboardButton("➡️ Далее", callback_data=f"go_next:{nxt}"))
    return row

def attach_nav(kb: InlineKeyboardMarkup | None, back: str | None = None, nxt: str | None = None) -> InlineKeyboardMarkup:
    """
    Приклеивает строку навигации к существующей InlineKeyboardMarkup.
    Если kb is None — создаёт только навигацию.
    """
    nav_row = nav_kb_row(back, nxt)
    if not nav_row:
        return kb or InlineKeyboardMarkup([])
    if kb is None:
        return InlineKeyboardMarkup([nav_row])
    # kb.inline_keyboard — list[list[InlineKeyboardButton]]
    buttons = [list(row) for row in kb.inline_keyboard]
    buttons.append(nav_row)
    return InlineKeyboardMarkup(buttons)


# Когда возвращаемся назад — нужно удалить данные шага, который нас уходит (чтобы не сохранять)
# mapping: target_step -> key_to_delete (это ключ данных *следующего* шага, который мы очищаем)
_delete_after_map = {
    "LOCATION": "point_types",
    "POINT_TYPE": "fish",
    "FISH_TYPE": "fishing",
    "FISHING_TYPE": "fishing_extra",
    "DETAIL": "coords",
    "COORDS": "temp",
    "TEMP": "photos",
    "PHOTOS": "comment",
    "COMMENT": "author",
    "AUTHOR": None,
}


# ----------------- Навигационные обработчики -----------------
async def go_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":", 1)
    if len(parts) < 2:
        return ConversationHandler.END
    target = parts[1]

    # Удаляем данные следующего шага (чтобы "Назад" отменял данные шага, с которого уходим)
    key_to_delete = _delete_after_map.get(target)
    if key_to_delete and key_to_delete in context.user_data:
        del context.user_data[key_to_delete]
        save_draft(update.effective_user.id, json.dumps(context.user_data))

    # Отправляем соответствующий экран (в точности как в оригинальном flow)
    if target == "LOCATION":
        await q.edit_message_text("🎣 Шаг 1: Выберите водоём:", reply_markup=attach_nav(make_location_kb(), None, "POINT_TYPE"))
        return LOCATION

    if target == "POINT_TYPE":
        # повторить точную клавиатуру с отметками, если есть
        chosen = context.user_data.get("point_types", [])
        await q.edit_message_text("Шаг 2: Выберите тип точки:", reply_markup=attach_nav(make_point_type_kb(chosen), "LOCATION", None))
        return POINT_TYPE

    if target == "FISH_TYPE":
        await q.edit_message_text("🎣 Шаг 3: Выберите вид рыбы:", reply_markup=attach_nav(make_fish_type_kb(), "POINT_TYPE", None))
        return FISH_TYPE

    if target == "FISHING_TYPE":
        await q.edit_message_text("Шаг 4: Выберите тип ловли:", reply_markup=attach_nav(make_fishing_type_kb(), "FISH_TYPE", None))
        return FISHING_TYPE

    if target == "DETAIL":
        # экран ввода дополнительного параметра
        await q.edit_message_text("Шаг 4.1: Введите параметр:", reply_markup=attach_nav(None, "FISHING_TYPE", "COORDS"))
        return DETAIL

    if target == "TEMP":
        await q.edit_message_text("Шаг 6: Температура:", reply_markup=attach_nav(make_temp_kb(), "COORDS", None))
        return TEMP

    if target == "PHOTOS":
        text = (
            "Шаг 7: Загрузите не больше 10 скриншотов.\n\n"
            "📸 Скриншоты должны отображать:\n"
            "• место ловли\n• садок\n• прикорм\n• карту\n• сборку\n\n"
            "Отправляйте скриншоты как обычные сообщения.\n"
            "Фотографии мониторов не принимаются .\n"
            "Когда закончите, нажмите кнопку «Далее» ."
        )
        # оригинально ты показывал кнопку "Далее" — сохраним её и добавим Back
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Далее", callback_data="photos_done")]])
        kb = attach_nav(kb, "TEMP", "COMMENT")
        await q.edit_message_text(text, reply_markup=kb)
        return PHOTOS

    if target == "COMMENT":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить", callback_data="skip_comment")]])
        kb = attach_nav(kb, "PHOTOS", "AUTHOR")
        await q.edit_message_text("Шаг 8: Добавьте комментарий или нажмите «Пропустить».", reply_markup=kb)
        return COMMENT

    if target == "AUTHOR":
        kb = attach_nav(None, "COMMENT", "PREVIEW")
        await q.edit_message_text("Шаг 9: Укажите свой игровой ник:", reply_markup=kb)
        return AUTHOR

    if target == "PREVIEW":
        text = build_post_text(context.user_data)
        kb = make_confirm_kb()
        kb = attach_nav(kb, "AUTHOR", None)
        await q.edit_message_text("Шаг 10: Предпросмотр:\n\n" + text, reply_markup=kb)
        return PREVIEW

    return ConversationHandler.END


async def go_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    parts = q.data.split(":", 1)
    if len(parts) < 2:
        return ConversationHandler.END
    target = parts[1]

    # Перейти к следующему экрану (без сохранения/изменения данных — просто навигация)
    if target == "POINT_TYPE":
        await q.edit_message_text("Шаг 2: Выберите тип точки:", reply_markup=attach_nav(make_point_type_kb(), "LOCATION", None))
        return POINT_TYPE

    if target == "FISH_TYPE":
        await q.edit_message_text("🎣 Шаг 3: Выберите вид рыбы:", reply_markup=attach_nav(make_fish_type_kb(), "POINT_TYPE", None))
        return FISH_TYPE

    if target == "FISHING_TYPE":
        await q.edit_message_text("Шаг 4: Выберите тип ловли:", reply_markup=attach_nav(make_fishing_type_kb(), "FISH_TYPE", None))
        return FISHING_TYPE

    if target == "DETAIL":
        await q.edit_message_text("Шаг 4.1: Введите параметр:", reply_markup=attach_nav(None, "FISHING_TYPE", "COORDS"))
        return DETAIL

    if target == "TEMP":
        await q.edit_message_text("Шаг 6: Температура:", reply_markup=attach_nav(make_temp_kb(), "COORDS", None))
        return TEMP

    if target == "PHOTOS":
        text = (
            "Шаг 7: Загрузите не больше 10 скриншотов.\n\n"
            "📸 Скриншоты должны отображать:\n"
            "• место ловли\n• садок\n• прикорм\n• карту\n• сборку\n\n"
            "Отправляйте скриншоты как обычные сообщения.\n"
            "Фотографии мониторов не принимаются .\n"
            "Когда закончите, нажмите кнопку «Далее» ."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Далее", callback_data="photos_done")]])
        kb = attach_nav(kb, "TEMP", "COMMENT")
        await q.edit_message_text(text, reply_markup=kb)
        return PHOTOS

    if target == "COMMENT":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить", callback_data="skip_comment")]])
        kb = attach_nav(kb, "PHOTOS", "AUTHOR")
        await q.edit_message_text("Шаг 8: Добавьте комментарий или нажмите «Пропустить».", reply_markup=kb)
        return COMMENT

    if target == "AUTHOR":
        await q.edit_message_text("Шаг 9: Укажите свой игровой ник:", reply_markup=attach_nav(None, "COMMENT", "PREVIEW"))
        return AUTHOR

    if target == "PREVIEW":
        text = build_post_text(context.user_data)
        kb = make_confirm_kb()
        kb = attach_nav(kb, "AUTHOR", None)
        await q.edit_message_text("Шаг 10: Предпросмотр:\n\n" + text, reply_markup=kb)
        return PREVIEW

    return ConversationHandler.END


# --------------------- Шаг 7. Фото (без изменений логики) ---------------------
async def photo_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Принимает до 10 изображений. Учитывает как обычные фото, так и документы
    с изображениями (если Telegram отправил фото как файл).
    """
    if not isinstance(context.user_data.get("photos"), list):
        context.user_data["photos"] = []
    photos = context.user_data["photos"]

    # --- Получаем file_id для фото или документа-картинки ---
    file_id = None
    if update.message:
        if update.message.photo:
            # обычное фото
            file_id = update.message.photo[-1].file_id
        elif update.message.document and update.message.document.mime_type.startswith("image/"):
            # изображение, отправленное как документ
            file_id = update.message.document.file_id

    # Если это не картинка — выходим
    if not file_id:
        return PHOTOS

    # --- Сохраняем, если нет дубля и не превышен лимит ---
    if file_id not in photos:
        if len(photos) >= 10:
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Далее", callback_data="photos_done")]])
            kb = attach_nav(kb, "TEMP", "COMMENT")
            await update.message.reply_text(
                "📸 Вы уже загрузили максимум 10 фото.\nНажмите «Далее», чтобы перейти к следующему шагу.",
                reply_markup=kb,
            )
            return PHOTOS

        photos.append(file_id)
        save_draft(update.effective_user.id, json.dumps(context.user_data))

    # --- Ответ пользователю ---
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Далее", callback_data="photos_done")]])
    kb = attach_nav(kb, "TEMP", "COMMENT")
    await update.message.reply_text(
        f"Фото сохранено ({len(photos)}/10).\nОтправьте ещё фото или нажмите «Далее».",
        reply_markup=kb,
    )
    return PHOTOS


from telegram import InlineKeyboardMarkup, InlineKeyboardButton

# --------------------- Старт ---------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return GREETING

    text = (
        "🎣 <b>Привет, рыбак!</b>\n"
        "Добро пожаловать в место, где делятся удачей, опытом и самыми жирными трофеями!\n\n"
        "Здесь ты можешь:\n"
        "• Похвастаться своим уловом 🐟\n"
        "• Поделиться рабочей точкой для фарма 🎯\n\n"
        "Чтобы всё было по красоте, укажи:\n"
        "📍 Водоём и координаты\n"
        "🎣 Вид рыбы\n"
        "🖼️ Скриншоты (до 10 шт.)\n"
        "🧢 Твой игровой ник\n\n"
        "Огромное <b>СПАСИБО</b> за вклад в развитие канала!\n"
        "Русская Рыбалка 4 — <b>Mazaii tv 🎣</b>"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📮 Предложить пост", callback_data="start_post")],
        [InlineKeyboardButton(
            "🔍 Поиск точки",
            url="https://t.me/s/MAZAII_TV?q=%23водоем_r4map"
        )]
    ])

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=kb
    )

    return GREETING


# --- ШАГ 1: выбор водоёма ---
from locations import ALL_LOCATIONS  # убедись, что импорт есть сверху

def make_location_kb(selected=None):
    buttons = []
    row = []

    for code, name in ALL_LOCATIONS.items():
        label = f"✅ {name}" if code == selected else name
        row.append(InlineKeyboardButton(label, callback_data=f"loc_{code}"))
        # Когда собрали 2 кнопки — переносим в новую строку
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Добавляем навигационные кнопки
    buttons.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="nav_back"),
        InlineKeyboardButton("✅ Подтвердить", callback_data="nav_next")
    ])

    return InlineKeyboardMarkup(buttons)


# --------------------- Шаги 1–6 ---------------------
async def location_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # Извлекаем выбранный водоём
    loc = q.data.split("_", 1)[1]
    context.user_data["location"] = loc

    # Обновляем клавиатуру, показывая выбранный вариант с галочкой
    await q.edit_message_reply_markup(reply_markup=make_location_kb(selected=loc))
    return LOCATION

async def location_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if "location" not in context.user_data:
        await q.answer("Выберите водоём перед продолжением ⛔", show_alert=True)
        return LOCATION

    await q.edit_message_text(
        "🎣 Шаг 2: Выберите тип точки:",
        reply_markup=make_point_type_kb()
    )
    return POINT_TYPE


async def location_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "🎣 Приветствую, рыболов!\n"
        "Нажмите «📮 Предложить пост», чтобы начать заново.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📮 Предложить пост", callback_data="start_post")]
        ])
    )
    return GREETING

# --- ШАГ 2: выбор типа точки ---
def make_point_type_kb(selected=None):
    """
    Клавиатура выбора типа точки (2 столбца, можно выбрать до двух вариантов)
    """
    point_types = [
        ("farm", "Фарм"),
        ("trophy", "Трофей"),
        ("vysek", "Высед"),
        ("quest", "Задание"),
    ]

    # приводим selected к множеству для удобства
    selected = set(selected or [])
    buttons = []
    row = []

    for code, label in point_types:
        text = f"✅ {label}" if code in selected else label
        row.append(InlineKeyboardButton(text, callback_data=f"pt_{code}"))
        if len(row) == 2:  # два в строке
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # навигация внизу
    buttons.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="nav_back"),
        InlineKeyboardButton("✅ Подтвердить", callback_data="nav_next"),
    ])
    return InlineKeyboardMarkup(buttons)


async def point_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    raw = q.data  # полностью callback_data, например "pt_farm" или "nav_next"

    # Навигация: Назад
    if raw == "nav_back":
        await q.edit_message_text(
            "📍 Шаг 1: Выберите водоём:",
            reply_markup=make_location_kb(selected=context.user_data.get("location"))
        )
        return LOCATION

    # Навигация: Далее
    if raw == "nav_next":
        # Проверяем, выбрано ли хотя бы одно значение (если нужно)
        chosen = context.user_data.get("point_types", [])
        if not chosen:
            # предупреждение пользователю (alert)
            await q.answer("Выберите хотя бы один тип точки перед продолжением.", show_alert=True)
            return POINT_TYPE

        await q.edit_message_text(
            "🎣 Шаг 3: Выберите вид рыбы:",
            reply_markup=make_fish_type_kb()
        )
        return FISH_TYPE

    # Если пришёл выбор типа (pt_...)
    if raw.startswith("pt_"):
        key = raw.split("_", 1)[1]
        chosen = set(context.user_data.get("point_types", []))

        # переключаем (до 2 значений одновременно)
        if key in chosen:
            chosen.remove(key)
        else:
            if len(chosen) < 2:
                chosen.add(key)
            else:
                # если уже 2 — показываем предупреждение
                await q.answer("Можно выбрать не более 2 типов.", show_alert=True)
                return POINT_TYPE

        context.user_data["point_types"] = list(chosen)
        await q.edit_message_reply_markup(reply_markup=make_point_type_kb(selected=chosen))
        return POINT_TYPE

    # Незнакомый callback — оставляем состояние
    await q.answer()
    return POINT_TYPE

# --- ШАГ 3: выбор вида рыбы ---
def make_fish_type_kb(selected=None):
    buttons = []
    fishes = ["Разнорыбица", "Написать самому"]
    row = []
    for fish in fishes:
        label = f"✅ {fish}" if fish == selected else fish
        row.append(InlineKeyboardButton(label, callback_data=f"fish_{fish}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Навигация
    buttons.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="fish_back"),
        InlineKeyboardButton("✅ Подтвердить", callback_data="fish_next")
    ])
    return InlineKeyboardMarkup(buttons)

async def fish_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data.replace("fish_", "")

    # Назад
    if data == "back":
        await q.edit_message_text(
            "📍 Шаг 2: Выберите тип точки:",
            reply_markup=make_point_type_kb(selected=context.user_data.get("point_type"))
        )
        return POINT_TYPE

    # Далее
    if data == "next":
        if "fish_type" not in context.user_data:
            await q.answer("Выберите рыбу или введите её вручную ⛔", show_alert=True)
            return FISH_TYPE
        await q.edit_message_text(
            "🎣 Шаг 4: Выберите тип ловли:",
            reply_markup=make_fishing_type_kb()
        )
        return FISHING_TYPE

    # Если выбрано «Написать самому» → ждём текст
    if data == "Написать самому":
        await q.edit_message_text("Введите название рыбы:")
        return FISH_TYPE_TEXT

    # Иначе — обычный выбор (ставим галочку)
    context.user_data["fish_type"] = data
    await q.edit_message_reply_markup(reply_markup=make_fish_type_kb(selected=data))
    return FISH_TYPE


# --- Шаг 4.1: ввод параметра после выбора типа ловли ---
async def extra_param_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимаем значение после выбора типа ловли (клипса, глубина, скорость и т.д.)"""
    value = update.message.text.strip()
    if not value:
        await update.message.reply_text("Введите корректное значение ⛔")
        return DETAIL

    context.user_data["fishing_extra"] = value

    await update.message.reply_text(
        f"✅ Значение принято: {value}\n\nТеперь нажмите «➡️ Далее», чтобы продолжить.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="go_back:FISHING_TYPE"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="go_next:COORDS")
            ]
        ])
    )
    return DETAIL


async def fish_type_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # пользователь вводит название рыбы вручную
    fish_name = update.message.text.strip()
    if not fish_name:
        await update.message.reply_text("Введите корректное название рыбы ⛔")
        return FISH_TYPE_TEXT

    context.user_data["fish_type"] = fish_name
    await update.message.reply_text(
        f"✅ Рыба: {fish_name}\n\nТеперь нажмите «✅ Подтвердить» чтобы продолжить.",
        reply_markup=make_fish_type_kb(selected="Написать самому")
    )
    return FISH_TYPE


# --- ШАГ 4: выбор типа ловли ---
def make_fishing_type_kb(selected=None):
    options = [
        ("Донка", "donka"),
        ("Поплавок", "poplavok"),
        ("Спиннинг", "spin"),
        ("Троллинг", "trol"),
        ("Пилкинг", "pilk")
    ]
    buttons = []
    for i in range(0, len(options), 2):
        row = []
        for label, key in options[i:i+2]:
            mark = "✅ " if selected == key else ""
            row.append(InlineKeyboardButton(f"{mark}{label}", callback_data=f"ft_{key}"))
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton("⬅️ Назад", callback_data="nav_back"),
        InlineKeyboardButton("✅ Подтвердить", callback_data="nav_next")
    ])
    return InlineKeyboardMarkup(buttons)


async def fishing_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Шаг 4: выбор типа ловли.
    Бот отмечает выбор галочкой и ждёт подтверждения.
    После нажатия «✅ Подтвердить» переходит к шагу ввода параметра.
    """
    q = update.callback_query
    await q.answer()
    data = q.data

    # Назад
    if data == "nav_back":
        await q.edit_message_text(
            "🎯 Шаг 3: Выберите вид рыбы:",
            reply_markup=make_fish_type_kb(selected=context.user_data.get("fish_type"))
        )
        return FISH_TYPE

    # Подтвердить
    if data in ("nav_next", "go_next:DETAIL"):
        if "fishing_type" not in context.user_data:
            await q.answer("Выберите тип ловли перед продолжением ⛔", show_alert=True)
            return FISHING_TYPE

        fishing_type = context.user_data["fishing_type"]

        prompts = {
            "poplavok": "🎣 Укажите глубину (например: 150 см.)",
            "spin": "🎣 Укажите скорость проводки (например: 15)",
            "donka": "🎣 Укажите клипсу (например: 15 м.)",
            "trol": "🎣 Укажите клипсу (например: 30 м.)",
            "pilk": "🎣 Укажите тип пилкинга (например: сильный)"
        }
        prompt_text = prompts.get(fishing_type, "🎣 Укажите параметр:")

        await q.edit_message_text(prompt_text)
        return DETAIL

    # Выбор типа ловли
    if data.startswith("ft_"):
        key = data.split("_", 1)[1]
        context.user_data["fishing_type"] = key
        context.user_data["fishing"] = key
        save_draft(update.effective_user.id, json.dumps(context.user_data))

        await q.edit_message_reply_markup(reply_markup=make_fishing_type_kb(selected=key))
        return FISHING_TYPE

    return FISHING_TYPE


async def fishing_detail_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Принимаем значение после выбора типа ловли (клипса, глубина и т. д.)
       Сохраняем под ключом 'fishing_extra' — чтобы оно попадало в предпросмотр и пост."""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Введите корректное значение ⛔")
        return DETAIL

    # сохраняем именно в fishing_extra (build_post_text читает fishing_extra)
    context.user_data["fishing_extra"] = text
    save_draft(update.effective_user.id, json.dumps(context.user_data))

    # подтверждаем и показываем кнопку Подтвердить (как было прежде)
    await update.message.reply_text(
        f"✅ Сохранено: {text}\n\nТеперь нажмите '✅ Подтвердить', чтобы перейти к следующему шагу.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="go_back:FISHING_TYPE"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="go_next:COORDS")
            ]
        ])
    )
    return DETAIL


# ---------- ШАГ 5: Координаты ----------
import re
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

def make_coordinates_kb():
    """Кнопки подтверждения координат (появляются только после ввода)."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="go_back:FISHING_TYPE"),
            InlineKeyboardButton("✅ Подтвердить", callback_data="go_next:TEMP")
        ]
    ])

async def coords_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход на шаг 5 — бот сразу предлагает ввести координаты (пример, без кнопок)."""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("📍 Шаг 5: Введите координаты (например: 56:123):")
    return COORDS_TEXT

async def coords_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода координат пользователем."""
    text = update.message.text.strip()

    # Строгая проверка: только формат 56:123
    if not re.fullmatch(r"-?\d{1,3}:\d{1,6}", text):
        await update.message.reply_text("⚠️ Неверный формат координат.\nВведите в формате: 56:123")
        return COORDS_TEXT

    # Сохраняем координаты
    context.user_data["coords"] = text
    save_draft(update.effective_user.id, json.dumps(context.user_data))

    # Показываем кнопки только после успешного ввода
    await update.message.reply_text(
        f"✅ Координаты сохранены: {text}\n\nТеперь нажмите «✅ Подтвердить», чтобы продолжить.",
        reply_markup=make_coordinates_kb()
    )
    return COORDS

async def coords_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Навигация: назад и подтвердить."""
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "go_back:FISHING_TYPE":
        await q.edit_message_text(
            "🎣 Шаг 4: Выберите тип ловли:",
            reply_markup=make_fishing_type_kb(selected=context.user_data.get("fishing_type"))
        )
        return FISHING_TYPE

    if data == "go_next:TEMP":
        if "coords" not in context.user_data:
            await q.answer("Введите координаты ⛔", show_alert=True)
            return COORDS

        save_draft(update.effective_user.id, json.dumps(context.user_data))
        await q.edit_message_text(
            "🌡 Шаг 6: Укажите температуру воды:",
            reply_markup=attach_nav(make_temp_kb(), "COORDS", "COMMENT")
        )
        return TEMP

    return COORDS


# ---------- ШАГ 6: Температура ----------
def make_temp_kb(selected=None):
    """Клавиатура для выбора температуры воды — только варианты,
       навигация добавляется вручную (⬅️ Назад / ➡️ Продолжить)."""
    buttons = [
        [
            InlineKeyboardButton(
                ("✅ Повышенная" if selected == "high" else "Повышенная"),
                callback_data="temp_high"
            ),
            InlineKeyboardButton(
                ("✅ Пониженная" if selected == "low" else "Пониженная"),
                callback_data="temp_low"
            )
        ],
        [
            InlineKeyboardButton(
                ("✅ Нормальная" if selected == "normal" else "Нормальная"),
                callback_data="temp_normal"
            ),
            InlineKeyboardButton(
                ("✅ Пропустить" if selected == "skip" else "Пропустить"),
                callback_data="temp_skip"
            )
        ]
    ]
    return InlineKeyboardMarkup(buttons)


async def temp_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора температуры и навигации на шаге 6."""
    q = update.callback_query
    await q.answer()
    cb = q.data  # например: temp_high / go_back:COORDS / go_next:COMMENT

    # --- Назад (из навигации) ---
    if cb.startswith("go_back:"):
        target = cb.split(":", 1)[1]
        if target == "COORDS":
            # Возврат к шагу 5 — показываем экран ввода координат (с прежней клавиатурой)
            await q.edit_message_text(
                "📍 Шаг 5: Укажите координаты:",
                reply_markup=attach_nav(make_coordinates_kb(), "FISHING_TYPE", "TEMP")
            )
            return COORDS

    # --- Нажали "Продолжить" (переход дальше) ---
    if cb.startswith("go_next:"):
        target = cb.split(":", 1)[1]
        if "temp" not in context.user_data:
            await q.answer("Выберите температуру или нажмите «Пропустить» ⛔", show_alert=True)
            return TEMP

        save_draft(update.effective_user.id, json.dumps(context.user_data))
        await q.edit_message_text(
            "📝 Шаг 7: Добавьте комментарий (необязательно):",
            reply_markup=make_comment_kb(has_comment=False)
        )
        return COMMENT

    # --- Нажали одну из кнопок temp_* ---
    if cb.startswith("temp_"):
        opt = cb.replace("temp_", "")  # high / low / normal / skip

        # Если выбрали "Пропустить" — сразу к комментарию
        if opt == "skip":
            context.user_data["temp"] = None
            save_draft(update.effective_user.id, json.dumps(context.user_data))
            await q.edit_message_text(
                "📝 Шаг 7: Добавьте комментарий (необязательно):",
                reply_markup=make_comment_kb(has_comment=False)
            )
            return COMMENT

        # Сохраняем выбор
        context.user_data["temp"] = opt
        save_draft(update.effective_user.id, json.dumps(context.user_data))

        # --- Составляем клавиатуру с отмеченной опцией и кнопкой "Продолжить" ---
        # Отмечаем выбранную опцию галочкой
        def label(name_key, label_text):
            return f"✅ {label_text}" if name_key == opt else label_text

        buttons = [
            [
                InlineKeyboardButton(label("high", "Повышенная"), callback_data="temp_high"),
                InlineKeyboardButton(label("low", "Пониженная"), callback_data="temp_low")
            ],
            [
                InlineKeyboardButton(label("normal", "Нормальная"), callback_data="temp_normal"),
                InlineKeyboardButton(label("skip", "Пропустить"), callback_data="temp_skip")
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="go_back:COORDS"),
                InlineKeyboardButton("✅ Продолжить", callback_data="go_next:COMMENT")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(buttons)

        # Текст выбранной температуры для вывода
        temp_text = "Нормальная" if opt == "normal" else ("Повышенная" if opt == "high" else "Пониженная")

        # Редактируем сообщение (показываем отмеченный выбор)
        try:
            await q.edit_message_text(
                f"🌡 Шаг 6: Укажите температуру воды:\n\nВы выбрали: *{temp_text}*",
                parse_mode="Markdown",
                reply_markup=reply_markup
            )
        except Exception:
            # Если не удалось отредактировать текст (иногда бывает), просто обновим клавиатуру
            try:
                await q.edit_message_reply_markup(reply_markup=reply_markup)
            except Exception:
                pass

        return TEMP

    # Если пришёл неожиданный callback — ничего не делаем
    await q.answer("Неизвестное действие ⛔")
    return TEMP



# ---------- ШАГ 7: Комментарий ----------

def make_comment_kb(has_comment=False):
    """Кнопки для шага 7: добавить комментарий или пропустить"""
    if not has_comment:
        buttons = [
            [InlineKeyboardButton("✏️ Написать комментарий", callback_data="comment_write")],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="go_back:TEMP"),
                InlineKeyboardButton("➡️ Пропустить", callback_data="comment_skip")
            ]
        ]
    else:
        buttons = [
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="go_back:TEMP"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="go_next:AUTHOR")
            ]
        ]
    return InlineKeyboardMarkup(buttons)


async def comment_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок на шаге комментария"""
    q = update.callback_query
    await q.answer()
    data = q.data

    # 🔙 Назад
    if data == "go_back:TEMP":
        await q.edit_message_text(
            "🌡 Шаг 6: Укажите температуру воды:",
            reply_markup=make_temp_kb(selected=context.user_data.get("temp"))
        )
        return TEMP

    # ⏭️ Пропустить
    if data == "comment_skip":
        context.user_data["comment"] = None
        save_draft(update.effective_user.id, json.dumps(context.user_data))
        return await author_start(update, context)

    # ✏️ Написать комментарий
    if data == "comment_write":
        await q.edit_message_text("Введите ваш комментарий:")
        return COMMENT_TEXT

    # ➡️ Далее
    if data == "go_next:AUTHOR":
        save_draft(update.effective_user.id, json.dumps(context.user_data))
        return await author_start(update, context)

    # если вдруг пришло что-то другое
    await q.answer("Неизвестное действие ⛔")
    return COMMENT


async def comment_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приём текста комментария"""
    text = update.message.text.strip()

    if not text:
        await update.message.reply_text("Комментарий не может быть пустым ⛔")
        return COMMENT_TEXT

    # сохраняем
    context.user_data["comment"] = text
    save_draft(update.effective_user.id, json.dumps(context.user_data))

    # показываем, что комментарий сохранён
    await update.message.reply_text(
        f"✅ Комментарий сохранён.\n\n"
        f"Нажмите «✅ Подтвердить», чтобы перейти к следующему шагу.",
        reply_markup=make_comment_kb(has_comment=True)
    )

    # остаёмся на шаге комментария
    return COMMENT


# ---------- ШАГ 8: Ввод ника ----------

def make_author_kb():
    """Кнопки для шага с вводом ника"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="go_back:COMMENT"),
            InlineKeyboardButton("✅ Подтвердить", callback_data="go_next:PHOTOS")
        ]
    ])


async def author_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Переход на шаг 8 — ввод ника"""
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "👤 Шаг 8: Укажите свой игровой ник:",
        reply_markup=make_author_kb()
    )
    return AUTHOR


# ---------- ШАГ 8: Автор ----------
async def author_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пользователь вводит ник → подтверждает и только потом идёт на фото"""
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Введите корректный ник ⛔")
        return AUTHOR

    # Сохраняем ник
    context.user_data["author"] = text
    save_draft(update.effective_user.id, json.dumps(context.user_data))

    # Показываем подтверждение
    await update.message.reply_text(
        f"✅ Ник сохранён: {text}\n\nТеперь нажмите «✅ Подтвердить», чтобы перейти к следующему шагу (фото).",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="go_back:COMMENT"),
                InlineKeyboardButton("✅ Подтвердить", callback_data="go_next:PHOTOS")
            ]
        ])
    )
    return AUTHOR


# ---------- ШАГ 9: Фото ----------

def make_photos_kb():
    """Кнопки для шага загрузки фото"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⬅️ Назад", callback_data="go_back:AUTHOR"),
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_screenshots")
        ]
    ])


async def photos_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает инструкцию по загрузке фото"""
    text = (
        "📸 <b>Шаг 9: Загрузите до 10 скриншотов.</b>\n\n"
        "<b>Скриншоты должны включать:</b>\n"
        "• 🎯 Место ловли\n"
        "• 🎒 Садок\n"
        "• 🧂 Прикорм\n"
        "• 🗺 Карту точки\n"
        "• 🎣 Сборку с наживкой\n\n"
        "📤 Отправляйте скриншоты <b>обычными сообщениями</b>.\n"
        "⚠️ Обязательно поставьте галочки:\n"
        "• «Сжимать фото»\n"
        "• «Группировать»\n\n"
        "🚫 <b>Фотографии монитора не принимаются.</b>\n\n"
        "Когда загрузите все изображения — нажмите «Подтвердить»."
    )

    await update.callback_query.edit_message_text(
        text=text,
        parse_mode="HTML",
        reply_markup=make_photos_kb()
    )
    return PHOTOS

async def photo_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приём до 10 скриншотов"""
    user_id = update.effective_user.id
    photos = context.user_data.get("photos", [])

    # Получаем file_id
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document and update.message.document.mime_type.startswith("image/"):
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("⛔ Отправьте именно скриншот (фото).")
        return PHOTOS

    # Проверка лимита
    if len(photos) >= 10:
        await update.message.reply_text(
            "📸 Вы уже загрузили 10 скриншотов — это максимум.",
            reply_markup=make_photos_kb()
        )
        return PHOTOS

    # Добавляем
    photos.append(file_id)
    context.user_data["photos"] = photos
    save_draft(user_id, json.dumps(context.user_data))

    await update.message.reply_text(
        f"✅ Скриншот добавлен ({len(photos)}/10).\n"
        "Когда закончите, нажмите «Подтвердить».",
        reply_markup=make_photos_kb()
    )
    return PHOTOS


async def photos_done_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """После загрузки фото → Предпросмотр"""
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "go_back:AUTHOR":
        await q.edit_message_text(
            "👤 Шаг 8: Укажите свой игровой ник:",
            reply_markup=make_author_kb()
        )
        return AUTHOR

    if data == "confirm_screenshots":
        save_draft(update.effective_user.id, json.dumps(context.user_data))
        text = build_post_text(context.user_data)
        kb = make_confirm_kb()
        kb = attach_nav(kb, "PHOTOS", None)
        await q.edit_message_text("Шаг 10: Предпросмотр:\n\n" + text, reply_markup=kb)
        return PREVIEW

    return PHOTOS


# --------------------- Сборка текста ---------------------
from locations import ALL_LOCATIONS  # импортируем словарь

def build_post_text(data: dict) -> str:
    # Справочники
    point_type_map = {
        "farm": "Фарм",
        "trophy": "Трофей",
        "vysek": "Высед",
        "quest": "Задание",
    }

    fish_map = {
        "mix":   "Разнорыбица",
        "carp":  "Карп",
        "pike":  "Щука",
        "perch": "Окунь",
        "bream": "Лещ",
    }

    fishing_map = {
        "donka":    "Донка кл.",
        "poplavok": "Поплавок гл.",
        "spin":     "Спиннинг ск.",
        "trol":     "Троллинг кл.",
        "pilk":     "Пилкинг",
    }

    temp_map = {
        "normal": "Нормальная",
        "high": "Повышенная",
        "low":  "Пониженная",
    }

    # Извлекаем данные
    location_code = data.get("location", "")
    types = data.get("point_types", [])
    fish_code = data.get("fish_type", "")
    fishing_code = data.get("fishing_type", "")
    extra = data.get("fishing_extra", "")
    coords = data.get("coords", "")
    temp_code = data.get("temp", "")
    author = data.get("author", "")
    comment = data.get("comment", "")

    # Преобразуем значения в текст
    lake = ALL_LOCATIONS.get(location_code, location_code)
    types_text = ", ".join(point_type_map.get(t, t) for t in types) if types else "—"
    fish = fish_map.get(fish_code, fish_code)
    fishing = fishing_map.get(fishing_code, fishing_code)
    temp = temp_map.get(temp_code, temp_code)

    hashtag = "#" + (
        lake.lower()
        .replace(" ", "_")
        .replace(".", "")
        .replace("ё", "е")
    )

    # Формируем строки
    lines = [
        f"📍 Водоём:  {hashtag}",
        f"🎯 Точка: {types_text}",
        f"🐟 Рыба: {fish}",
        f"🎣 Ловля: {fishing}" + (f" {extra}" if extra else ""),
        f"🗺 Координаты: {coords}",
    ]

    # 🌡 Добавляем температуру, только если выбрана
    if temp_code and str(temp_code).lower() not in ("none", "null", "nan", ""):
        lines.append(f"🌡 Температура: {temp}")

    if comment:
        lines.append(f"📝 Комментарий: {comment}")

    if author:
        lines.append(f"👤 Автор: {author}")
    else:
        lines.append("👤 Автор: неизвестен")

    return "\n".join(lines)


# --------------------- Модерация ---------------------
import os, json, asyncio, logging

from telegram.error import TelegramError, TimedOut
from telegram.ext import ConversationHandler

logger = logging.getLogger(__name__)

async def confirm_publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить пост в модераторский чат для подтверждения"""
    q = update.callback_query
    await q.answer()

    data = context.user_data
    base_text = build_post_text(data)
    author = data.get("author", "user")
    photos = data.get("photos", [])
    user_id = update.effective_user.id

    mod_chat = _mod_chat_id()
    if not mod_chat:
        await q.edit_message_text("❗ Ошибка: MOD_CHAT_ID не задан.")
        return ConversationHandler.END

    # Убираем кнопки у пользователя
    try:
        await q.edit_message_text("✅ Ваш пост отправлен на модерацию.")
    except Exception:
        pass

    # --- 1. Отправляем сам пост (без клавиатуры) ---
    if photos:
        if len(photos) > 1:
            media = [InputMediaPhoto(media=photos[0], caption=base_text, parse_mode="HTML")]
            for pid in photos[1:]:
                media.append(InputMediaPhoto(media=pid))
            await context.bot.send_media_group(chat_id=mod_chat, media=media)
        else:
            await context.bot.send_photo(
                chat_id=mod_chat,
                photo=photos[0],
                caption=base_text,
                parse_mode="HTML"
            )
    else:
        await context.bot.send_message(chat_id=mod_chat, text=base_text, parse_mode="HTML")

    # --- 2. Отдельное сообщение с кнопками ---
    msg = await context.bot.send_message(
        chat_id=mod_chat,
        text=f"👤 Автор: {author}\n\nОдобрить пост?",
        reply_markup=make_moderation_kb(user_id),
        parse_mode="HTML",
    )

    # сохраняем chat_id и message_id, чтобы удалить позже
    context.bot_data[f"moderation_msg_{user_id}"] = (msg.chat.id, msg.message_id)
    logger.info("Save moderation msg: chat=%s id=%s", msg.chat.id, msg.message_id)

    return ConversationHandler.END

async def confirm_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена отправки поста на модерацию"""
    q = update.callback_query
    await q.answer()

    # Сообщение пользователю
    try:
        await q.edit_message_text("❌ Отправка поста отменена.")
    except Exception:
        # если не удалось отредактировать, отправляем новое
        await context.bot.send_message(chat_id=update.effective_user.id,
                                       text="❌ Отправка поста отменена.")

    return ConversationHandler.END


# ---------------------- Модерация: одобрить пост ----------------------
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.error import TelegramError, TimedOut
import asyncio, json, os, logging

logger = logging.getLogger(__name__)

async def mod_approve(update, context):
    """
    Одобряет пост и публикует в канал.
    Кнопка «📨 ПРЕДЛОЖИТЬ ПОСТ» встроена в текст как кликабельная ссылка.
    Работает при любом типе поста (текст, одно фото, медиагруппа).
    """
    q = update.callback_query
    await q.answer()

    # --- убираем клавиатуру у модератора ---
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception as e:
        logger.warning("Не удалось убрать клавиатуру: %s", e)

    # --- получаем данные черновика ---
    parts = q.data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("Некорректный callback.")
        return

    user_id = int(parts[1])
    draft = load_draft(user_id)
    if not draft:
        await q.edit_message_text("Черновик не найден.")
        return

    data = json.loads(draft)
    text = build_post_text(data)

    # добавляем кнопку в текст (кликабельная ссылка)
    text += "\n\n📨 <b><a href='https://t.me/MazaiiBot?start=post'>ПРЕДЛОЖИТЬ ПОСТ</a></b>"

    photos = data.get("photos", [])
    if isinstance(photos, str):
        photos = [photos]
    elif not isinstance(photos, list):
        photos = list(photos)

    channel = os.getenv("CHANNEL_ID") or os.getenv("MAIN_CHANNEL_ID")

    try:
        if channel:
            if photos:
                if len(photos) > 1:
                    # 📸 Несколько фото (медиагруппа)
                    media = [InputMediaPhoto(media=photos[0], caption=text, parse_mode="HTML")]
                    for pid in photos[1:]:
                        media.append(InputMediaPhoto(media=pid))
                    await context.bot.send_media_group(
                        chat_id=channel,
                        media=media,
                        disable_notification=True,
                        protect_content=True
                    )
                else:
                    # 🖼 Одно фото
                    await context.bot.send_photo(
                        chat_id=channel,
                        photo=photos[0],
                        caption=text,
                        parse_mode="HTML",
                        disable_notification=True,
                        protect_content=True
                    )
            else:
                # 📝 Без фото
                await context.bot.send_message(
                    chat_id=channel,
                    text=text,
                    parse_mode="HTML",
                    disable_notification=True,
                    protect_content=True
                )

    except TimedOut:
        logger.error("⏳ TimedOut при публикации поста.")
        return
    except TelegramError as e:
        logger.error("Ошибка при публикации поста: %s", e)
        return

    # --- сообщение автору ---
    await context.bot.send_message(
        chat_id=user_id,
        text="✅ Ваш пост опубликован."
    )

    # --- обновляем сообщение в модераторской ---
    chat_id, msg_id = context.bot_data.get(f"moderation_msg_{user_id}", (None, None))
    if chat_id and msg_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text="✅ Пост одобрен и опубликован.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning("Не удалось обновить текст модерации: %s", e)
    else:
        logger.warning("moderation_msg_%s не найден в bot_data", user_id)

    delete_draft(user_id)



async def mod_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отклонить пост"""
    q = update.callback_query
    await q.answer()

    parts = q.data.split(":")
    if len(parts) < 2:
        await q.edit_message_text("Некорректный callback.")
        return
    user_id = int(parts[1])

    delete_draft(user_id)
    try:
        await context.bot.send_message(user_id, "❌ Ваш пост отклонён модератором.")
    except Exception:
        pass

    await q.edit_message_text("🚫 Отклонено модератором.")


# --------------------- Универсальная отмена ---------------------
from telegram import Update
from telegram.ext import ConversationHandler, ContextTypes
import logging

logger = logging.getLogger(__name__)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 🔥 КРИТИЧНО — чистим данные пользователя
    context.user_data.clear()

    logger.info(
        f"Conversation cancelled by user {update.effective_user.id}"
    )

    text = "🔄 Действие отменено. Начинаем заново."

    if update.message:
        await update.message.reply_text(text)

    elif update.callback_query:
        q = update.callback_query
        await q.answer()
        try:
            await q.edit_message_text(text)
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=text
            )

    return ConversationHandler.END


# --------------------- Алиасы для ConversationHandler ---------------------
async def greeting_next(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Срабатывает, когда пользователь нажимает кнопку «➡️ Далее» на экране приветствия.
    Здесь мы запускаем тот же сценарий, что и при /start post:
    - очищаем список фото в user_data,
    - отправляем сообщение «Шаг 1: Выберите водоём»
      вместе с клавиатурой make_location_kb,
    - переводим ConversationHandler в состояние LOCATION.
    """
    query = update.callback_query
    await query.answer()                           # подтверждаем нажатие
    await query.edit_message_reply_markup(None)     # убираем клавиатуру «Далее»

    # Подготовка данных, как при /start post
    context.user_data["photos"] = []

# --------------------- Запуск сценария ---------------------
async def start_post_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data.clear()
    context.user_data["photos"] = []

    await query.message.reply_text(
        "🎣 Шаг 1: Выберите водоём:",
        reply_markup=make_location_kb()
    )

    return LOCATION


    # Отправляем пользователю сообщение с клавиатурой выбора водоёма
    await query.message.reply_text(
        "🎣 Шаг 1: Выберите водоём:",
        reply_markup=attach_nav(make_location_kb(), None, "POINT_TYPE")
    )

    # Возвращаем состояние LOCATION, чтобы ConversationHandler знал, что делать дальше
    return LOCATION

async def detail_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await extra_param_text(update, context)

async def coords_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await coords_input(update, context)

async def comment_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # правильный вызов — comment_input (в коде есть comment_input)
    return await comment_input(update, context)


# --------------------- ConversationHandler ---------------------
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start_command),
    ],

    states={
        GREETING: [
            CallbackQueryHandler(start_post_callback, pattern="^start_post$")
        ],

        LOCATION: [
            CallbackQueryHandler(location_chosen, pattern="^loc_"),
            CallbackQueryHandler(location_next, pattern="^nav_next$"),
            CallbackQueryHandler(location_back, pattern="^nav_back$"),
        ],

        POINT_TYPE: [
            CallbackQueryHandler(point_type_chosen, pattern=r"^(pt_|nav_)"),
        ],

        FISH_TYPE: [
            CallbackQueryHandler(fish_type_chosen, pattern=r"^(fish_|nav_)"),
        ],

        FISH_TYPE_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, fish_type_text)
        ],

        FISHING_TYPE: [
            CallbackQueryHandler(fishing_type_chosen, pattern=r"^(ft_|nav_)"),
            CallbackQueryHandler(go_back, pattern="^go_back:FISH_TYPE$"),
            CallbackQueryHandler(go_next, pattern="^go_next:DETAIL$"),
            CallbackQueryHandler(coords_start, pattern="^go_next:COORDS$")
        ],

        DETAIL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, fishing_detail_input),
            CallbackQueryHandler(go_back, pattern="^go_back:FISHING_TYPE$"),
            CallbackQueryHandler(coords_start, pattern="^go_next:COORDS$")
        ],

        COORDS: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, coords_input),
            CallbackQueryHandler(coords_chosen, pattern="^go_next:TEMP$")
        ],

        TEMP: [
            CallbackQueryHandler(temp_chosen, pattern="^(temp_|go_)")
        ],

        PHOTOS: [
            MessageHandler(filters.PHOTO | filters.Document.IMAGE, photo_add),
            CallbackQueryHandler(photos_done_btn, pattern="^(go_|confirm_screenshots$)"),
        ],

        COMMENT: [
            CallbackQueryHandler(comment_chosen, pattern="^comment_|^go_"),
        ],

        COMMENT_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, comment_input)
        ],

        AUTHOR: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, author_entered),
            CallbackQueryHandler(go_back, pattern="^go_back:COMMENT$"),
            CallbackQueryHandler(photos_start, pattern="^go_next:PHOTOS$"),
            CallbackQueryHandler(go_next, pattern="^go_next:PREVIEW$")
        ],

        PREVIEW: [
            CallbackQueryHandler(confirm_publish, pattern="^confirm_publish$"),
            CallbackQueryHandler(confirm_cancel, pattern="^confirm_cancel$"),
            CallbackQueryHandler(go_back, pattern="^go_back:AUTHOR$")
        ],
    },

    fallbacks=[
        CommandHandler("cancel", cancel),
    ],

    allow_reentry=True,
    per_message=False,
)

