from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from PRILOJENIA1.telegram_bot import TelegramAPIError, telegram_api


class Command(BaseCommand):
    help = "Настраивает Telegram webhook для подтверждения номера телефона"

    def add_arguments(self, parser):
        parser.add_argument(
            "--url",
            required=True,
            help="Публичный HTTPS-адрес обработчика /telegram/webhook/",
        )

    def handle(self, *args, **options):
        webhook_url = options["url"].strip()
        parsed_url = urlparse(webhook_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise CommandError("Webhook должен иметь публичный HTTPS-адрес.")
        if not settings.TELEGRAM_WEBHOOK_SECRET:
            raise CommandError("Сначала задайте переменную TELEGRAM_WEBHOOK_SECRET.")
        try:
            telegram_api(
                "setWebhook",
                {
                    "url": webhook_url,
                    "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
                    "allowed_updates": ["message"],
                },
            )
        except TelegramAPIError as error:
            raise CommandError(f"Не удалось настроить Telegram webhook: {error}") from error

        self.stdout.write(self.style.SUCCESS("Telegram webhook настроен."))
