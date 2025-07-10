import logging
import os
import tempfile

import json
from threading import Thread
from datetime import datetime
from typing import Dict, Any
from reply import handle_group_reply
from pathlib import Path

from flask import Flask, request, abort

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    InputMediaDocument,
    InputMediaPhoto,
    Message
)

from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    CallbackContext,
    CallbackQueryHandler,
    ContextTypes
)


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG) # change to INFO
logger = logging.getLogger(__name__)

GROUP_ID = os.getenv("GROUP_ID")

(SELECT_ADDRESS, INPUT_TEXT, UPLOAD_FILES, INPUT_PHONE, CONFIRMATION) = range(5)

ADDRESS_LIST = [
    "Складской проезд, 4",
    "Проспект Бакунина, 13",
    "Перекупной переулок, 18",
    "Полтавская улица, 5",
    "Боровая улица, 8И",
    "Крапивный переулок, 3А"
]


def build_application() -> Application:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in environment variables.")

    return Application.builder().token(token).build()


def load_counter() -> int:
    try:
        with open("data/counter.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("counter", 1)
    except FileNotFoundError:
        initial = int(os.getenv("INITIAL_COUNTER_VALUE", "1"))
        save_counter(initial)
        logger.info(f"[counter] counter.json was not found, used counter value from the environment: {initial}")
        return initial
    except json.JSONDecodeError:
        logger.warning("[counter] reading error counter.json, counter value reset to 1")
        return 1


def save_counter(counter: int) -> None:
    os.makedirs("data", exist_ok=True)
    try:
        with open("data/counter.json", "w", encoding="utf-8") as f:
            json.dump({"counter": counter}, f, ensure_ascii=False)
        logger.info(f"[counter] counter value saved: {counter}")
    except Exception as e:
        logger.error(f"[counter] failed to save counter to file: {e}")




"""
before:
def save_request_to_file(data: Dict[str, Any]) -> None:
    os.makedirs("data", exist_ok=True)
    try:
        with open("data/requests.json", "a", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        logger.error(f"Failed to save request to file: {e}")

after:
def save_request_to_file(new_request: dict) -> None:
    path = Path("data/requests.json")
    os.makedirs(path.parent, exist_ok=True)
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []

        data.append(new_request)

        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при сохранении заявки: {e}")

after:
"""
def save_request_to_file(new_request: dict) -> None:
    """
    Атомарное сохранение заявки в файл requests.json
    
    Args:
        new_request: Словарь с данными заявки, содержащий:
            - timestamp: ISO строка времени создания
            - counter: Уникальный номер заявки
            - user: Имя пользователя или username
            - user_id: ID пользователя в Telegram
            - address: Адрес из заявки
            - text: Текст заявки
            - phone: Телефон из заявки
            - files: Список файлов (если есть)
            - file_types: Типы файлов (если есть)
            - status: Статус заявки ("open" по умолчанию)
    """
    path = Path("data/requests.json")
    
    try:
        # Создаем директорию если не существует
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Читаем существующие данные
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = []
        
        # Устанавливаем статус по умолчанию если не указан
        if "status" not in new_request:
            new_request["status"] = "open"
        
        # Добавляем новую заявку
        data.append(new_request)
        
        # Атомарная запись через временный файл
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=path.parent, encoding="utf-8", suffix=".tmp"
        ) as tf:
            json.dump(data, tf, ensure_ascii=False, indent=2)
            temp_path = Path(tf.name)
        
        # Атомарная замена файла
        temp_path.replace(path)
        
        logger.info(f"Заявка №{new_request.get('counter')} успешно сохранена в {path.name}")
        
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Ошибка при сохранении заявки: {e}")
        # Удаляем временный файл если он остался
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise




def build_address_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(addr, callback_data=f"addr_{i}")] for i, addr in enumerate(ADDRESS_LIST)]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: CallbackContext):
    logger.info(f"Received /start from user {update.effective_user.id}")
    context.user_data.clear()
    context.user_data['continue_button_msg_id'] = None
    context.user_data['continue_button_sent'] = False

    reply_markup = build_address_keyboard()
    message_text = "Выберите Ваш объект:"

    if update.message:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
    
    return SELECT_ADDRESS


async def address_selected(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()

    idx = int(query.data.split("_")[1])
    selected_address = ADDRESS_LIST[idx]
    context.user_data['address'] = selected_address

    await context.bot.send_message(chat_id=query.message.chat_id, text=f"Ваш объект: {selected_address}.")
    await context.bot.send_message(chat_id=query.message.chat_id, text="Введите текст обращения:")
    
    return INPUT_TEXT


async def input_text(update: Update, context: CallbackContext) -> int:
    context.user_data['text'] = update.message.text
    context.user_data['files'] = []
    context.user_data['file_types'] = []
    context.user_data['continue_button_msg_id'] = None
    context.user_data['continue_button_sent'] = False

    continue_message = await update.message.reply_text(
	"Опционально добавьте вложения и (или) нажмите <b>Продолжить</b>.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Продолжить", callback_data="continue_phone")]]
        )
    )
    context.user_data['continue_button_msg_id'] = continue_message.message_id
    context.user_data['continue_button_sent'] = True
    
    return UPLOAD_FILES


async def upload_files(update: Update, context: CallbackContext):
    files = context.user_data.get("files", [])
    file_types = context.user_data.get("file_types", [])
    
    if update.message.document:
        f = await update.message.document.get_file()
        files.append(f.file_id)
        file_types.append("document")
        file_name = update.message.document.file_name # or ""
    elif update.message.photo:
        f = await update.message.photo[-1].get_file()
        files.append(f.file_id)
        file_types.append("photo")

    context.user_data["files"] = files
    context.user_data["file_types"] = file_types

    if context.user_data.get('continue_button_msg_id') and context.user_data.get('continue_button_sent'):
        try:
            files_count = len(files)
            files_text = "вложение" if files_count == 1 else "вложения" if files_count < 5 else "вложений"
            
            await context.bot.edit_message_text(
                chat_id=update.message.chat_id,
                message_id=context.user_data['continue_button_msg_id'],
                text=f"Опционально добавьте вложения и (или) нажмите <b>Продолжить</b>.\n\n Добавлено <b>{files_count}</b> {files_text}.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Продолжить", callback_data="continue_phone")]]
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to update continue button message: {e}")
            continue_message = await update.message.reply_text(
                f"Добавлено <b>{len(files)}</b> {files_text}",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("Продолжить", callback_data="continue_phone")]]
                )
            )
            context.user_data['continue_button_msg_id'] = continue_message.message_id

    return UPLOAD_FILES


async def files_continue(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except:
        pass
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Введите Ваши контактные данные:"
    )
    return INPUT_PHONE


async def input_phone(update: Update, context: CallbackContext):
    context.user_data["phone"] = update.message.text
    address = context.user_data["address"]
    text = context.user_data["text"]
    phone = context.user_data["phone"]
    files = context.user_data.get("files", [])

    preview = (f"Ваш объект: <b>{address}</b>.\n"
               f"Ваши контактные данные: {phone}.\n\n"
               f"Текст обращения:\n{text}\n\n"
               f"Количество вложений: <b>{len(files)}</b>.\n")

    buttons = [[
        InlineKeyboardButton("Отправить", callback_data="send"),
        InlineKeyboardButton("Отмена", callback_data="cancel")
    ]]
    await update.message.reply_text(
        preview,
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML"
    )
    return CONFIRMATION


async def new_request(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    # Clear user data for new request
    context.user_data.clear()
    context.user_data['continue_button_msg_id'] = None
    context.user_data['continue_button_sent'] = False

    reply_markup = build_address_keyboard()
    message_text = "Выберите Ваш объект:"

    # Send new message instead of editing to preserve previous messages
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=message_text,
        reply_markup=reply_markup
    )

    return SELECT_ADDRESS


async def confirmation(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    recipient_chat = os.getenv("GROUP_ID")
    if not recipient_chat:
        raise RuntimeError("GROUP_ID is not set in environment variables.")

    if query.data == "cancel":
        return await start(update, context)

    try:
        if 'application_counter' not in context.application.bot_data:
            context.application.bot_data['application_counter'] = load_counter()
        
        counter = context.application.bot_data.get("application_counter", 1)
        context.application.bot_data["application_counter"] = counter + 1
        save_counter(counter + 1)
        
        user = query.from_user
        address = context.user_data["address"]
        text = context.user_data["text"]
        phone = context.user_data["phone"]
        files = context.user_data.get("files", [])
        file_types = context.user_data.get("file_types", [])

        full_message = (f"\U0001F4DF Зарегистрировано новое обращение <code>#{counter}</code>.\n\n"
                        f"Объект: <b>{address}</b>.\n"
                        f"Контактные данные отправителя: {phone} ({user.mention_html()}).\n\n"
                        f"{text}\n")
                        
        """
        before:
        save_request_to_file({
            "timestamp": datetime.now().isoformat(),
            "counter": counter,
            "user": user.username or user.full_name,
            "user_id": user.id,
            "address": address,
            "text": text,
            "phone": phone,
            "files": files,
            "file_types": file_types
        })
        after:
        """
        save_request_to_file({
            "timestamp": datetime.now().isoformat(),
            "number": counter,
            "user": user.username or user.full_name,
            "user_id": user.id,
            "address": address,
            "text": text,
            "phone": phone,
            "files": files,
            "file_types": file_types,
            "status": 1
        })
        
        # Send message to recipient_chat
        await context.bot.send_message(chat_id=recipient_chat, text=full_message, parse_mode="HTML")
        
        # Send files if any
        media_docs = [InputMediaDocument(media=fid) for fid, t in zip(files, file_types) if t == "document"]
        media_photos = [InputMediaPhoto(media=fid) for fid, t in zip(files, file_types) if t == "photo"]

        if media_docs:
            await context.bot.send_media_group(chat_id=recipient_chat, media=media_docs)
        if media_photos:
            await context.bot.send_media_group(chat_id=recipient_chat, media=media_photos)
            
        # Remove inline keyboard from preview message
        await query.edit_message_reply_markup(reply_markup=None)
        
        # Send confirmation message with success status and "New Request" button
        new_request_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("Новое обращение", callback_data="new_request")
        ]])
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"\U0001F3F7 Спасибо. Ваше обращение <code>#{counter}</code> зарегистрировано. Мы свяжемся с Вами.",
            reply_markup=new_request_button,
            parse_mode="HTML"
        )
        
    except Exception as e:
        logger.error(f"Error in confirmation handler: {e}")
        
        # Remove inline keyboard from preview message even on error
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
            
        # Send error message with "New Request" button
        new_request_button = InlineKeyboardMarkup([[
            InlineKeyboardButton("Новое обращение", callback_data="new_request")
        ]])
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="\U0001F6F8 Что-то пошло не так... Попробуйте снова.",
            reply_markup=new_request_button
        )

    # End conversation - don't restart automatically
    return ConversationHandler.END


async def cancel(update: Update, context: CallbackContext):
    
    # Send "New Request" button after cancellation
    new_request_button = InlineKeyboardMarkup([[
        InlineKeyboardButton("Новое обращение", callback_data="new_request")
    ]])
    
    await update.message.reply_text(
        "Обращение отменено.",
        reply_markup=new_request_button
    )
    
    return ConversationHandler.END


def flask_app_from_bot() -> None:
    flask_app = Flask(__name__)
    
    @flask_app.route("/ping")
    def ping() -> str:
        key = request.args.get("key")
        if key != os.getenv("PING_KEY"):
            logging.warning(f"Unauthorized ping attempt from {request.remote_addr} with key={key}")
            abort(403)
        logging.info(f"Received authorized ping from {request.remote_addr}")

        return "It's Alive!"

    def run_flask() -> None:
        flask_app.run(host="0.0.0.0", port=8080)


    Thread(target=run_flask).start()


def main():
    application = build_application()
    application.bot_data['application_counter'] = load_counter()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start),
            CallbackQueryHandler(new_request, pattern=r"^new_request$")
        ],
        states={
            SELECT_ADDRESS: [CallbackQueryHandler(address_selected)],
            INPUT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_text)],
            UPLOAD_FILES: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, upload_files),
                CallbackQueryHandler(files_continue, pattern=r"^continue_phone$")
            ],
            INPUT_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, input_phone)],
            CONFIRMATION: [CallbackQueryHandler(confirmation, pattern=r"^(send|cancel)$")]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(new_request, pattern=r"^new_request$"))


    application.add_handler(MessageHandler(
        filters.REPLY & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
        handle_group_reply
    ))


    flask_app_from_bot()
    application.run_polling()

if __name__ == '__main__':
    main()
