import logging
import re
from pathlib import Path
from telegram import Update, Message, Chat
from telegram.ext import ContextTypes
from conversation import _load_json


logger = logging.getLogger(__name__)


def get_request_number(request: str) -> int | None:
    if not request:
        return None

    match = re.search(r".*Зарегистрировано новое обращение\s#(\d+)", request)
    if match:
        try:
            return int(match.group(1))
        except (ValueError, IndexError):
            return None


def get_user_id(request_number: int) -> int | None:
    try:
        data = _load_json(Path("/data/requests.json"))
        if not isinstance(data, list):
            logger.error("'/data/requests.json' contains incorrect data.")
            return None

        for request in data:
            if request.get("number") == request_number:
                return request.get("user_id")

        logger.warning(f"Request #{request_number} was not found in the '/data/requests.json'.")
    except Exception as e:
        logger.error(f"Error retrieving the User ID from Request #{request_number} ({e}).")


async def _send_reply(message: Message, context: ContextTypes.DEFAULT_TYPE, request_number: int, user_id: int) -> bool:
    try:
        if message.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"\U0001F4DF Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.text}",
                parse_mode="HTML"
            )
            return True
        elif message.photo:
            photo = message.photo[1]
            await context.bot.send_photo(
                chat_id=user_id,
                photo=photo.file_id,
                caption=f"\U0001F4F7 Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
            return True
        elif message.animation:
            await context.bot.send_animation(
                chat_id=user_id,
                animation=message.animation.file_id,
                caption=f"\U0001F4FC Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
            return True
        elif message.video:
            await context.bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=f"\U0001F4FC Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
            return True
        elif message.audio:
            await context.bot.send_audio(
                chat_id=user_id,
                audio=message.audio.file_id,
                caption=f"\U0001F4E3 Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
            return True
        elif message.voice:
            await context.bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id,
                caption=f"\U0001F4E3 Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
            return True
        elif message.document:
            await context.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=f"\U0001F4C3 Получен ответ на Ваше обращение <code>#{request_number}</code>.\n\n{message.caption or ''}",
                parse_mode="HTML"
            )
            return True
        else:
            logger.debug("Unsupported Response type.")
            return False
    except Exception as e:
        logger.error(f"An error occurred while sending the Response {type(message)} ({e}).")
        return False


async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug("Start Handle Chat Reply.")

    message: Message = update.effective_message
    if not message:
        return

    if not message.reply_to_message:
        logger.debug("No Reply.")
        return

    request = (message.reply_to_message or message.reply_to_caption)
    request_number = get_request_number(request.text)
    if not request_number:
        logger.debug("Could not get the Request Number.")
        return

    logger.debug(f"Request number received: #{request_number}.")


    """
    Maybe, future features:

    if is_request_closed(request_number):
        try: 
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Обращение <code>#{request_number}</code> закрыто его автором. Отправка ответа невозможна.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Could not notify about the Request #{request_number} closure ({e}).")
        return
    """


    user_id = get_user_id(request_number)
    if not user_id:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Не удалось определить получателя для Вашего ответа на обращение <code>#{request_number}</code>. Используйте контактные данные автора обращения, чтобы связаться с ним.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Could not report a problem identifying the recipient User ID ({e}).")
        return

    logger.debug(f"User ID received: {user_id}.")

    try:
        result = await _send_reply(message, context, request_number, user_id)
        if result:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Ваш ответ на обращение <code>#{request_number}</code> доставлен автору.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Could not send a Response to the Request #{request_number} ({e}).")
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Не удалось доставить Ваш ответ на обращение <code>#{request_number}</code>. Используйте контактные данные автора обращения, чтобы связаться с ним.",
                parse_mode="HTML"
            )
        except Exception as f:
            logger.error(f"Failed to report a problem with the delivery of the Response to the Request #{request_number}. ({f})")
