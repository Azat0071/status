import json
import logging
import urllib.error
import urllib.request

from django.conf import settings


logger = logging.getLogger(__name__)


class TelegramAPIError(Exception):
    pass


def telegram_api(method, payload):
    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        raise TelegramAPIError("Не задан TELEGRAM_BOT_TOKEN.")

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        logger.exception("Не удалось выполнить запрос к Telegram Bot API.")
        raise TelegramAPIError("Telegram временно недоступен.") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        logger.exception("Telegram Bot API вернул некорректный ответ.")
        raise TelegramAPIError("Получен некорректный ответ Telegram.") from error

    if not result.get("ok"):
        logger.error("Telegram Bot API error: %s", result.get("description", "unknown"))
        raise TelegramAPIError("Telegram не принял запрос.")
    return result.get("result")


def send_contact_request(chat_id):
    return telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": (
                "Для подтверждения аккаунта нажмите кнопку ниже и отправьте "
                "свой номер телефона. Telegram передаст контакт только после "
                "вашего подтверждения."
            ),
            "reply_markup": {
                "keyboard": [
                    [{"text": "Подтвердить мой номер", "request_contact": True}]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        },
    )


def send_bot_message(chat_id, text):
    return telegram_api(
        "sendMessage",
        {
            "chat_id": chat_id,
            "text": text,
            "reply_markup": {"remove_keyboard": True},
        },
    )
