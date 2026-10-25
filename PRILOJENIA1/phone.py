import re

from django.core.exceptions import ValidationError


def normalize_phone(value):
    phone = re.sub(r"[\s().-]", "", value.strip())
    if phone.startswith("00"):
        phone = f"+{phone[2:]}"
    if not re.fullmatch(r"\+[1-9]\d{7,14}", phone):
        raise ValidationError(
            "Введите номер в международном формате, например +996700123456."
        )
    return phone
