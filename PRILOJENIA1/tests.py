import tempfile
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import SESSION_KEY
from django.utils.crypto import get_random_string

from .models import Product, ProductSize


class BootstrapAdminCommandTests(TestCase):
    def test_creates_admin_from_environment_without_printing_password(self):
        password = get_random_string(40)
        output = StringIO()
        with patch.dict(
            "os.environ",
            {
                "ADMIN_USERNAME": "render_admin",
                "ADMIN_PASSWORD": password,
                "ADMIN_EMAIL": "admin@example.com",
            },
            clear=True,
        ):
            call_command("bootstrap_admin", stdout=output)

        user = get_user_model().objects.get(username="render_admin")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.email, "admin@example.com")
        self.assertNotIn(password, output.getvalue())

    def test_existing_admin_is_not_changed_on_restart(self):
        password = get_random_string(40)
        user = get_user_model().objects.create_superuser(
            username="render_admin",
            email="before@example.com",
            password=password,
        )
        output = StringIO()
        with patch.dict(
            "os.environ",
            {
                "ADMIN_USERNAME": "render_admin",
                "ADMIN_PASSWORD": get_random_string(40),
                "ADMIN_EMAIL": "after@example.com",
            },
            clear=True,
        ):
            call_command("bootstrap_admin", stdout=output)

        user.refresh_from_db()
        self.assertTrue(user.check_password(password))
        self.assertEqual(user.email, "before@example.com")
        self.assertIn("already exists", output.getvalue())

    def test_missing_environment_configuration_is_a_noop(self):
        output = StringIO()
        with patch.dict("os.environ", {}, clear=True):
            call_command("bootstrap_admin", stdout=output)

        self.assertIn("skipped", output.getvalue())
        self.assertFalse(get_user_model().objects.exists())

    def test_partial_environment_configuration_fails_explicitly(self):
        with patch.dict("os.environ", {"ADMIN_USERNAME": "render_admin"}, clear=True):
            with self.assertRaisesMessage(CommandError, "ADMIN_USERNAME and ADMIN_PASSWORD"):
                call_command("bootstrap_admin")


class HomePageTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.override_media = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.override_media.enable()

    def tearDown(self):
        self.override_media.disable()
        self.media_dir.cleanup()

    def test_root_url_renders_home_page(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "glavnaia_stranisa.html")
        self.assertContains(response, 'id="products-data"')
        self.assertContains(response, "Каталог скоро появится")

    def test_available_products_are_rendered_as_json_for_catalog(self):
        product = Product.objects.create(
            name="Пальто",
            category=Product.Category.OUTER,
            price=25000,
            description="Шерстяное пальто",
            image=SimpleUploadedFile(
                "coat.png",
                (
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                    b"\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00"
                    b"\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00"
                    b"IEND\xaeB`\x82"
                ),
                content_type="image/png",
            ),
        )
        ProductSize.objects.create(product=product, size="M", quantity=3)
        ProductSize.objects.create(product=product, size="L", quantity=2)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["products"][0]["name"], product.name)
        self.assertEqual(response.context["products"][0]["sizes"], [
            {"size": "L", "quantity": 2},
            {"size": "M", "quantity": 3},
        ])
        self.assertEqual(response.context["products"][0]["totalStock"], 5)
        self.assertContains(response, "/media/products/coat.png")

    def test_unavailable_products_are_not_shown(self):
        Product.objects.create(
            name="Скрытый товар",
            category=Product.Category.KNIT,
            price=1000,
            description="Не показывать на сайте",
            image=SimpleUploadedFile(
                "hidden.png",
                (
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
                    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
                    b"\x00\x00\x00\x0bIDAT\x08\xd7c\xf8\xcf\xc0\x00\x00"
                    b"\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00"
                    b"IEND\xaeB`\x82"
                ),
                content_type="image/png",
            ),
            is_available=False,
        )

        response = self.client.get("/")

        self.assertNotContains(response, "Скрытый товар")

    def test_admin_product_form_has_image_and_product_fields(self):
        user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=None,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("admin:PRILOJENIA1_product_add"))

        self.assertEqual(response.status_code, 200)
        for field in (
            "name",
            "sku",
            "category",
            "price",
            "description",
            "image",
            "color",
            "material",
        ):
            self.assertContains(response, f'name="{field}"')
        self.assertContains(response, 'name="sizes-0-size"')
        self.assertContains(response, 'name="sizes-0-quantity"')


class AdminProfileTests(TestCase):
    def setUp(self):
        self.original_password = get_random_string(40)
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=self.original_password,
        )
        self.client.force_login(self.user)

    def test_admin_dashboard_shows_catalog_statistics_and_profile(self):
        response = self.client.get(reverse("admin:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Управление товарами")
        self.assertContains(response, "Профиль и пароль")
        self.assertEqual(response.context["dashboard_products_count"], 0)

    def test_admin_can_change_and_save_profile_name(self):
        response = self.client.post(
            reverse("admin_profile"),
            {
                "action": "profile",
                "username": "status_manager",
                "first_name": "Азат",
                "last_name": "Тест",
                "email": "manager@example.com",
            },
        )

        self.assertRedirects(response, reverse("admin_profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "status_manager")
        self.assertEqual(self.user.get_full_name(), "Азат Тест")
        self.assertEqual(self.user.email, "manager@example.com")

    def test_admin_can_change_password_without_being_logged_out(self):
        new_password = get_random_string(40)
        response = self.client.post(
            reverse("admin_profile"),
            {
                "action": "password",
                "old_password": self.original_password,
                "new_password1": new_password,
                "new_password2": new_password,
            },
        )

        self.assertRedirects(response, reverse("admin_profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertEqual(
            int(self.client.session[SESSION_KEY]),
            self.user.pk,
        )
