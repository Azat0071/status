import os

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import DEFAULT_DB_ALIAS, transaction
from django.contrib.auth.password_validation import validate_password


class Command(BaseCommand):
    help = "Create an initial administrator from environment variables, if configured."

    def handle(self, *args, **options):
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "")
        email = os.environ.get("ADMIN_EMAIL", "").strip()

        if not username and not password and not email:
            self.stdout.write("Admin bootstrap skipped: ADMIN_* variables are not set.")
            return
        if not username or not password:
            raise CommandError("Set both ADMIN_USERNAME and ADMIN_PASSWORD.")

        User = get_user_model()
        username_field = User.USERNAME_FIELD
        if email:
            try:
                validate_email(email)
            except ValidationError as error:
                raise CommandError("ADMIN_EMAIL must be a valid email address.") from error

        using = options.get("database") or DEFAULT_DB_ALIAS
        with transaction.atomic(using=using):
            manager = User._default_manager.db_manager(using)
            existing_user = manager.filter(**{username_field: username}).first()
            if existing_user is not None:
                if not (existing_user.is_staff and existing_user.is_superuser):
                    raise CommandError(
                        f"User '{username}' already exists but is not an administrator."
                    )
                self.stdout.write(
                    self.style.WARNING(
                        f"Administrator '{username}' already exists; account unchanged."
                    )
                )
                return

            user = User(**{username_field: username})
            if email and User.EMAIL_FIELD:
                setattr(user, User.EMAIL_FIELD, email)
            user.is_active = True
            user.is_staff = True
            user.is_superuser = True
            try:
                validate_password(password, user)
            except ValidationError as error:
                raise CommandError(
                    "ADMIN_PASSWORD does not meet the configured password requirements."
                ) from error

            user.set_password(password)
            user.save(using=using)

        self.stdout.write(
            self.style.SUCCESS(f"Administrator '{username}' created successfully.")
        )
