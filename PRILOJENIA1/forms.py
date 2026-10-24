from django import forms
from django.contrib.auth import get_user_model


class AdminProfileForm(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Имя пользователя для входа",
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Электронная почта",
        }
