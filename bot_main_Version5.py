"""
Основной модуль бота (финальная версия архива):
- формы продажи/покупки
- поддержка фото (file_id)
- поиск с листанием
- профиль (активные объявления)
- команда /del — удаляет только свои объявления
- команда /deleted — "секретная", удаляет любое объявление по номеру
- секретные команды /vipp, /zakrepp, /unzakrep — доступны любому, кто их знает
"""
import logging
import json
from typing import Dict, List, Optional
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
)
from .config import BOT_TOKEN, ADMIN_ID, CHANNEL_USERNAME, LOG_LEVEL
from .db import init_db, ensure_user, add_ad, get_ad, get_ads, delete_ad, get_user_ads, set_vip, get_user, set_pin

# logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger(__name__)

# States
STATE_SELECT_SERVER = 1
STATE_SELECT_CATEGORY = 2
STATE_SELECT_TYPE = 3
STATE_FILL_FIELDS = 4
STATE_ATTACH_PHOTOS = 5
STATE_CONFIRM = 6

SERVERS = ["TEXAS", "FLORIDA", "NEVADA", "HAWAII", "INDIANA"]
CATEGORIES = [
    "Машина",
    "Аксессуар",
    "Недвижимость",
    "Бизнес",
    "SIM-карта",
    "Предметы",
    "Номерные знаки",
    "Костюмы",
]

TYPES_BASE = ["Ивент", "BattlePass", "Обычный"]

FIELDS_TEMPLATE = {
    "Машина": ["Ваш ник", "Название машины", "Цена", "Контакт (TG/VK)"],
    "Недвижимость": ["Ваш ник", "Номер дома/адрес", "Цена", "Контакт (TG/VK)"],
    "Аксессуар": ["Ваш ник", "Название аксессуара", "Цена", "Контакт (TG/VK)"],
    "SIM-карта": ["Ваш ник", "Номер сим-карты (пример)", "Цена", "Контакт (TG/VK)"],
    "Бизнес": ["Ваш ник", "Название бизнеса", "Доход за 1 день", "Цена", "Контакт (TG/VK)"],
    "Предметы": ["Ваш ник", "Название предмета", "Цена", "Контакт (TG/VK)"],
    "Номерные знаки": ["Ваш ник", "Номерной знак (пример)", "Цена", "Контакт (TG/VK)"],
    "Костюмы": ["Ваш ник", "Название костюма", "Цена", "Контакт (TG/VK)"],
}

FIELDS_TEMPLATE_BUY = {
    "Машина": ["Ваш ник", "Название машины", "Бюджет", "Контакт (TG/VK)"],
    "Недвижимость": ["Ваш ник", "Тип дома (класс, город)", "Бюджет", "Контакт (TG/VK)"],
    "Аксессуар": ["Ваш ник", "Название аксессуара", "Бюджет", "Контакт (TG/VK)"],
    "SIM-карта": ["Ваш ник", "Пример сим-карты", "Бюджет", "Контакт (TG/VK)"],
    "Бизнес": ["Ваш ник", "Желаемый бизнес", "Желаемый доход за 1 день", "Бюджет", "Контакт (TG/VK)"],
    "Предметы": ["Ваш ник", "Название предмета", "Бюджет", "Контакт (TG/VK)"],
    "Номерные знаки": ["Ваш ник", "Пример номерного знака", "Бюджет", "Контакт (TG/VK)"],
    "Костюмы": ["Ваш ник", "Название костюма", "Бюджет", "Контакт (TG/VK)"],
}

GREETING_TEXT = (
    "Добро пожаловать, здесь вы можете быстрее и удобнее продать или купить: "
    "машину, аксессуар, недвижимость, аксессуары, бизнесы, сим-карта, номерные знаки авто.\n\n"
    "Перед публикацией вы можете приложить фото товара при соответствующем шаге."
)

def make_main_keyboard():
    kb = [
        [InlineKeyboardButton("Продать", callback_data="action:sell"), InlineKeyboardButton("Купить", callback_data="action:buy")],
        [InlineKeyboardButton("Поиск", callback_data="action:search"), InlineKeyboardButton("Профиль", callback_data="action:profile")],
        [InlineKeyboardButton("VIP / Подписка", callback_data="action:vip"), InlineKeyboardButton("Услуги", callback_data="action:services")],
        [InlineKeyboardButton("Техподдержка", url="https://t.me/azdanm")]
    ]
    return InlineKeyboardMarkup(kb)

async def check_subscription_required(app, user_id):
    if not CHANNEL_USERNAME:
        return True
    try:
        member = await app.bot.get_chat_member(CHANNEL_USERNAME, user_id)
        status = member.status
        return status not in ("left", "kicked")
    except Exception as e:
        logger.warning("Не удалось проверить подписку: %s", e)
        return True

def format_ad_message(ad: Dict) -> str:
    fields = json.loads(ad["fields"] or "{}")
    lines = [f"#{ad['id']} • {ad['server']} • {ad['category']} • {'VIP' if ad['vip'] else ''}{' 📌' if ad['pinned'] else ''}"]
    lines.append(f"Действие: {'Продать' if ad['action']=='sell' else 'Купить'}")
    lines.append(f"Тип: {ad['type']}")
    for k, v in fields.items():
        lines.append(f"{k}: {v}")
    lines.append(f"Автор: {ad.get('username') or ad.get('user_id')}")
    return "\n".join(lines)

# Handlers
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username)
    keyboard = make_main_keyboard()
    await update.message.reply_text(GREETING_TEXT, reply_markup=keyboard)

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "action:sell" or data == "action:buy":
        context.user_data["action"] = "sell" if data.endswith("sell") else "buy"
        kb = [[InlineKeyboardButton(s, callback_data=f"server:{s}")] for s in SERVERS]
        kb.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
        await query.message.reply_text("Выберите сервер:", reply_markup=InlineKeyboardMarkup(kb))
        return STATE_SELECT_SERVER
    elif data == "action:search":
        kb = [[InlineKeyboardButton(s, callback_data=f"search_server:{s}")] for s in SERVERS]
        kb.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
        await query.message.reply_text("Выберите сервер для поиска:", reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    elif data == "action:profile":
        user_id = query.from_user.id
        ads = get_user_ads(user_id)
        if not ads:
            await query.message.reply_text("У вас нет активных объявлений.", reply_markup=make_main_keyboard())
        else:
            text = "Ваши объявления:\n" + "\n\n".join([f"#{a['id']} • {a['server']} • {a['category']} • {a['type']} • {'Продать' if a['action']=='sell' else 'Купить'}" for a in ads])
            await query.message.reply_text(text, reply_markup=make_main_keyboard())
        return ConversationHandler.END
    elif data == "action:vip":
        text = (
            "VIP: При покупке подписки VIP, ваши объявления после публикации будут видны всем пользователям.\n"
            "Стоимость 25₽ навсегда.\n\nЧтобы купить, напишите в личные сообщения: @azdanm"
        )
        await query.message.reply_text(text, reply_markup=make_main_keyboard())
        return ConversationHandler.END
    elif data == "action:services":
        text = (
            "1. Закреп объявления в нашем боте на 24ч — стоимость 15₽.\n\n"
            "Информация: ваше объявление будет закреплено в боте на главной странице, и его будут видеть все пользователи бота.\n\n"
            "2. Услуга вечный VIP — при покупке все ваши опубликованные объявления будут видны всем пользователям бота. Стоимость: 50₽\n\n"
            "Чтобы приобрести услуги, напишите в личные сообщения: @azdanm"
        )
        kb = [[InlineKeyboardButton("Назад", callback_data="menu:back")]]
        await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
        return ConversationHandler.END
    elif data == "menu:back":
        await query.message.edit_text(GREETING_TEXT, reply_markup=make_main_keyboard())
        return ConversationHandler.END

async def select_server_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    server = query.data.split(":", 1)[1]
    context.user_data["server"] = server
    kb = [[InlineKeyboardButton(c, callback_data=f"category:{c}")] for c in CATEGORIES]
    kb.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
    await query.message.reply_text(f"Сервер: {server}\nВыберите категорию:", reply_markup=InlineKeyboardMarkup(kb))
    return STATE_SELECT_CATEGORY

async def select_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split(":", 1)[1]
    context.user_data["category"] = category
    kb = [[InlineKeyboardButton(t, callback_data=f"type:{t}")] for t in TYPES_BASE]
    kb.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
    await query.message.reply_text(f"Категория: {category}\nВыберите тип объявления (Ивент / BattlePass / Обычный):", reply_markup=InlineKeyboardMarkup(kb))
    return STATE_SELECT_TYPE

async def select_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    type_ = query.data.split(":", 1)[1]
    context.user_data["type"] = type_
    action = context.user_data.get("action", "sell")
    category = context.user_data.get("category")
    if action == "buy":
        template = FIELDS_TEMPLATE_BUY.get(category, ["Ваш ник", "Описание", "Бюджет/Цена", "Контакт (TG/VK)"])
    else:
        template = FIELDS_TEMPLATE.get(category, ["Ваш ник", "Название", "Цена", "Контакт (TG/VK)"])
    context.user_data["fields_keys"] = template
    context.user_data["fields_values"] = {}
    context.user_data["current_field_idx"] = 0
    key = template[0]
    await query.message.reply_text(f"Введите: {key}\n\n(Вы можете отправить любое текстовое описание; также можно приложить фотографию товара позже)")
    return STATE_FILL_FIELDS

async def fill_fields_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message and update.message.text else None
    if not text:
        await update.message.reply_text("Пожалуйста, введите текст для данного поля.")
        return STATE_FILL_FIELDS
    idx = context.user_data.get("current_field_idx", 0)
    keys = context.user_data.get("fields_keys", [])
    if idx >= len(keys):
        await update.message.reply_text("Все поля уже заполнены.")
        return STATE_ATTACH_PHOTOS
    key = keys[idx]
    context.user_data["fields_values"][key] = text
    idx += 1
    context.user_data["current_field_idx"] = idx
    if idx < len(keys):
        next_key = keys[idx]
        await update.message.reply_text(f"Введите: {next_key}")
        return STATE_FILL_FIELDS
    else:
        kb = [
            [InlineKeyboardButton("Прикрепить фото (отправьте фото ниже)", callback_data="attach:photos")],
            [InlineKeyboardButton("Пропустить", callback_data="attach:skip")],
        ]
        await update.message.reply_text("Все поля заполнены. Теперь вы можете приложить фото товара (до 5) или пропустить.", reply_markup=InlineKeyboardMarkup(kb))
        context.user_data["photos"] = []
        return STATE_ATTACH_PHOTOS

async def attach_photos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "attach:skip":
        return await confirm_ad_prompt(query.message, context)
    elif data == "attach:photos":
        await query.message.reply_text("Отправьте фото (до 5). Когда закончите — отправьте /done. Или нажмите Пропустить.")
        return STATE_ATTACH_PHOTOS

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data.get("photos", [])
    if not update.message.photo:
        await update.message.reply_text("Отправьте фото или /done для завершения.")
        return STATE_ATTACH_PHOTOS
    file_id = update.message.photo[-1].file_id
    photos.append(file_id)
    context.user_data["photos"] = photos
    if len(photos) >= 5:
        await update.message.reply_text("Добавлено 5 фото (макс).")
        return await post_confirm_from_user(update, context)
    else:
        await update.message.reply_text(f"Фото принято ({len(photos)}/5). Отправьте ещё или /done чтобы продолжить.")
        return STATE_ATTACH_PHOTOS

async def done_photos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await post_confirm_from_user(update, context)

async def post_confirm_from_user(update_or_message, context):
    if isinstance(update_or_message, Update):
        message = update_or_message.message
    else:
        message = update_or_message
    return await confirm_ad_prompt(message, context)

async def confirm_ad_prompt(message, context):
    action = context.user_data.get("action")
    server = context.user_data.get("server")
    category = context.user_data.get("category")
    type_ = context.user_data.get("type")
    fields = context.user_data.get("fields_values", {})
    photos = context.user_data.get("photos", [])
    lines = [f"Предварительный просмотр объявления ({'Продать' if action=='sell' else 'Купить'}):"]
    lines.append(f"Сервер: {server}")
    lines.append(f"Категория: {category}")
    lines.append(f"Тип: {type_}")
    for k, v in fields.items():
        lines.append(f"{k}: {v}")
    lines.append("Вы можете приложить фото (если уже добавлены — будут отображены).")
    text = "\n".join(lines)
    kb = [[InlineKeyboardButton("Опубликовать", callback_data="confirm:publish"), InlineKeyboardButton("Отмена", callback_data="confirm:cancel")]]
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))
    if photos:
        try:
            media = [InputMediaPhoto(pid) for pid in photos[:10]]
            await message.reply_media_group(media)
        except Exception:
            pass
    return STATE_CONFIRM

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "confirm:cancel":
        await query.message.reply_text("Отмена публикации.", reply_markup=make_main_keyboard())
        context.user_data.clear()
        return ConversationHandler.END
    elif data == "confirm:publish":
        user = query.from_user
        allowed = await check_subscription_required(context.application, user.id)
        if not allowed:
            await query.message.reply_text("Для публикации объявлений необходимо подписаться на канал. Затем нажмите /start и повторите.", reply_markup=make_main_keyboard())
            context.user_data.clear()
            return ConversationHandler.END
        action = context.user_data.get("action")
        server = context.user_data.get("server")
        category = context.user_data.get("category")
        type_ = context.user_data.get("type")
        fields = context.user_data.get("fields_values", {})
        photos = context.user_data.get("photos", [])
        u = get_user(user.id)
        vip_user = bool(u and u.get("vip"))
        ad_id = add_ad(user.id, user.username or "", server, category, type_, action, fields, photos, vip=vip_user)
        await query.message.reply_text(f"Ваше объявление опубликовано. Номер объявления #{ad_id}", reply_markup=make_main_keyboard())
        context.user_data.clear()
        return ConversationHandler.END

async def search_server_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    server = query.data.split(":", 1)[1]
    context.user_data["search_server"] = server
    kb = [[InlineKeyboardButton(c, callback_data=f"search_category:{c}")] for c in CATEGORIES]
    kb.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
    await query.message.reply_text(f"Поиск — сервер: {server}\nВыберите категорию:", reply_markup=InlineKeyboardMarkup(kb))

async def search_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.split(":", 1)[1]
    server = context.user_data.get("search_server")
    kb = [
        [InlineKeyboardButton("Все", callback_data=f"search_do:all:{category}")],
        [InlineKeyboardButton("Продать", callback_data=f"search_do:sell:{category}"), InlineKeyboardButton("Купить", callback_data=f"search_do:buy:{category}")],
        [InlineKeyboardButton("Назад", callback_data="menu:back")],
    ]
    await query.message.reply_text(f"Сервер: {server}\nКатегория: {category}\nВыберите действие для поиска:", reply_markup=InlineKeyboardMarkup(kb))

async def search_do_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action_filter, category = query.data.split(":", 2)
    server = context.user_data.get("search_server")
    action = None if action_filter == "all" else action_filter
    ads = get_ads(server=server, category=category, action=action)
    if not ads:
        await query.message.reply_text("Объявлений не найдено.", reply_markup=make_main_keyboard())
        return
    context.user_data["search_results"] = [a["id"] for a in ads]
    context.user_data["search_idx"] = 0
    await show_search_result(query.message, context)

async def show_search_result(message, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("search_idx", 0)
    results = context.user_data.get("search_results", [])
    if not results:
        await message.reply_text("Нет результатов.")
        return
    ad_id = results[idx]
    ad = get_ad(ad_id)
    if not ad:
        await message.reply_text("Ошибка: объявление не найдено.")
        return
    text = format_ad_message(ad)
    nav_row = []
    if idx > 0:
        nav_row.append(InlineKeyboardButton("◀️ Назад", callback_data="search_nav:prev"))
    if idx < len(results) - 1:
        nav_row.append(InlineKeyboardButton("Вперёд ▶️", callback_data="search_nav:next"))
    kb2 = [
        InlineKeyboardButton("Пожаловаться/Техподдержка", url="https://t.me/azdanm"),
        InlineKeyboardButton("Назад в меню", callback_data="menu:back"),
    ]
    rows = [nav_row] if nav_row else []
    rows.append(kb2)
    await message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))
    photos = json.loads(ad.get("photos") or "[]")
    if photos:
        try:
            media = [InputMediaPhoto(pid) for pid in photos[:10]]
            await message.reply_media_group(media)
        except Exception:
            pass

async def search_nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    direction = query.data.split(":", 1)[1]
    idx = context.user_data.get("search_idx", 0)
    results = context.user_data.get("search_results", [])
    if direction == "next" and idx < len(results) - 1:
        context.user_data["search_idx"] = idx + 1
        await show_search_result(query.message, context)
    elif direction == "prev" and idx > 0:
        context.user_data["search_idx"] = idx - 1
        await show_search_result(query.message, context)
    else:
        await query.message.reply_text("Дальше нет объявлений.")

# Команда для удаления своих объявлений
async def del_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /del <id> — удаляет только объявление, принадлежащее отправителю
    user = update.effective_user
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /del <номер_объявления>")
        return
    try:
        ad_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    ad = get_ad(ad_id)
    if not ad:
        await update.message.reply_text("Объявление не найдено.")
        return
    if ad["user_id"] != user.id:
        await update.message.reply_text("Вы можете удалять только свои объявления.")
        return
    ok = delete_ad(ad_id)
    if ok:
        await update.message.reply_text(f"Ваше объявление #{ad_id} удалено.")
    else:
        await update.message.reply_text("Не удалось удалить объявление.")

# СЕКРЕТНЫЕ КОМАНДЫ — доступны любому пользователю, который их знает
async def deleted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /deleted <id> — удаляет любое объявление (секретная команда)
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /deleted <номер_объявления>")
        return
    try:
        ad_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный ID.")
        return
    ok = delete_ad(ad_id)
    if ok:
        await update.message.reply_text(f"Объявление #{ad_id} удалено.")
    else:
        await update.message.reply_text("Объявление не найдено или не удалось удалить.")

async def vipp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /vipp <user_id> — выдать VIP указанному пользователю (секретная команда)
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /vipp <user_id>")
        return
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный user_id.")
        return
    set_vip(target_id, True)
    await update.message.reply_text(f"Пользователю {target_id} выдан VIP.")

async def zakrepp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /zakrepp <ad_id> — закрепить объявление (секретная команда)
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /zakrepp <ad_id>")
        return
    try:
        ad_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный id.")
        return
    set_pin(ad_id, True)
    await update.message.reply_text(f"Объявление #{ad_id} закреплено.")

async def unzakrep_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # /unzakrep <ad_id> — открепить объявление (секретная команда)
    args = context.args
    if not args:
        await update.message.reply_text("Использование: /unzakrep <ad_id>")
        return
    try:
        ad_id = int(args[0])
    except ValueError:
        await update.message.reply_text("Неверный id.")
        return
    set_pin(ad_id, False)
    await update.message.reply_text(f"Объявление #{ad_id} откреплено.")

async def unknown_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда. Используйте меню.", reply_markup=make_main_keyboard())

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Произошла ошибка: %s", context.error)

def build_app():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(menu_callback, pattern=r"^action:(sell|buy)$")],
        states={
            STATE_SELECT_SERVER: [CallbackQueryHandler(select_server_callback, pattern=r"^server:")],
            STATE_SELECT_CATEGORY: [CallbackQueryHandler(select_category_callback, pattern=r"^category:")],
            STATE_SELECT_TYPE: [CallbackQueryHandler(select_type_callback, pattern=r"^type:")],
            STATE_FILL_FIELDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, fill_fields_handler)],
            STATE_ATTACH_PHOTOS: [
                CallbackQueryHandler(attach_photos_callback, pattern=r"^attach:(photos|skip)$"),
                MessageHandler(filters.PHOTO & ~filters.COMMAND, photo_handler),
                CommandHandler("done", done_photos_command),
            ],
            STATE_CONFIRM: [CallbackQueryHandler(confirm_callback, pattern=r"^confirm:(publish|cancel)$")],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: u.message.reply_text("Операция отменена."))],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(conv)

    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^action:"))
    app.add_handler(CallbackQueryHandler(select_server_callback, pattern=r"^server:"))
    app.add_handler(CallbackQueryHandler(select_category_callback, pattern=r"^category:"))
    app.add_handler(CallbackQueryHandler(select_type_callback, pattern=r"^type:"))
    app.add_handler(CallbackQueryHandler(search_server_callback, pattern=r"^search_server:"))
    app.add_handler(CallbackQueryHandler(search_category_callback, pattern=r"^search_category:"))
    app.add_handler(CallbackQueryHandler(search_do_callback, pattern=r"^search_do:"))
    app.add_handler(CallbackQueryHandler(search_nav_callback, pattern=r"^search_nav:"))
    app.add_handler(CallbackQueryHandler(confirm_callback, pattern=r"^confirm:"))
    app.add_handler(CallbackQueryHandler(attach_photos_callback, pattern=r"^attach:"))
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))

    # Команда удаления своего объявления
    app.add_handler(CommandHandler("del", del_command))
    # Секретные команды доступны любому (если знает)
    app.add_handler(CommandHandler("deleted", deleted_command))
    app.add_handler(CommandHandler("vipp", vipp_command))
    app.add_handler(CommandHandler("zakrepp", zakrepp_command))
    app.add_handler(CommandHandler("unzakrep", unzakrep_command))

    app.add_handler(MessageHandler(filters.COMMAND, unknown_handler))
    app.add_error_handler(error_handler)
    return app

async def main():
    init_db()
    app = build_app()
    logger.info("Бот стартует...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())