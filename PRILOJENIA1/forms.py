from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .models import CustomerProfile
from .phone import normalize_phone


User = get_user_model()


class AdminProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email")
        labels = {
            "username": "Имя пользователя для входа",
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Электронная почта",
        }


class CustomerRegistrationForm(forms.Form):
    phone = forms.CharField(
        label="Номер телефона",
        max_length=30,
        widget=forms.TextInput(
            attrs={"autocomplete": "tel", "placeholder": "+996700123456"}
        ),
    )
    first_name = forms.CharField(label="Имя и фамилия", max_length=150)
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data["phone"])
        existing_profile = CustomerProfile.objects.select_related("user").filter(
            phone=phone
        ).first()
        if existing_profile:
            raise ValidationError("Этот номер уже зарегистрирован.")
        if User.objects.filter(username=phone).exists():
            raise ValidationError("Этот номер уже используется.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Пароли не совпадают.")
        elif password1:
            try:
                from django.contrib.auth.password_validation import validate_password

                validate_password(password1)
            except ValidationError as error:
                self.add_error("password1", error)
        return cleaned_data


class CustomerLoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Номер телефона",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "tel",
                "placeholder": "+996700123456",
            }
        ),
    )

    def clean(self):
        raw_phone = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if raw_phone and password:
            try:
                phone = normalize_phone(raw_phone)
            except ValidationError as error:
                self.add_error("username", error)
                return self.cleaned_data
            profile = CustomerProfile.objects.select_related("user").filter(
                phone=phone
            ).first()
            if profile is not None:
                self.user_cache = authenticate(
                    self.request,
                    username=profile.user.get_username(),
                    password=password,
                )
                if self.user_cache is None:
                    raise self.get_invalid_login_error()
                self.confirm_login_allowed(self.user_cache)
                self.cleaned_data["username"] = phone
                return self.cleaned_data
        raise self.get_invalid_login_error()


class CustomerProfileForm(forms.Form):
    first_name = forms.CharField(label="Имя и фамилия", max_length=150)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        initial = kwargs.pop("initial", {})
        initial.update({
            "first_name": user.first_name,
        })
        super().__init__(*args, initial=initial, **kwargs)

    def save(self):
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.save(update_fields=("first_name",))
