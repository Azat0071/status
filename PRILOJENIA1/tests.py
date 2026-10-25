import json
import tempfile
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import SESSION_KEY
from django.utils.crypto import get_random_string

from .models import (
    CustomerProfile,
    Order,
    OrderItem,
    PendingPhoneRegistration,
    Product,
    ProductSize,
)


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
        self.assertContains(
            response,
            'href="#home" aria-current="page" class="text-[#b83b4b] hover:text-white',
        )
        self.assertContains(response, "Мой профиль")

    def test_collection_page_renders_collection_catalog(self):
        response = self.client.get(reverse("collection"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "collection.html")
        self.assertContains(response, "НАЙДИТЕ СВОЙ ОБРАЗ")
        self.assertContains(response, 'data-filter="knit"')
        self.assertContains(response, "Коллекция скоро появится")
        self.assertContains(
            response,
            'aria-current="page" class="text-[#b83b4b] hover:text-white',
        )
        self.assertContains(response, "Мой профиль")

    def test_collection_marks_products_with_no_stock(self):
        Product.objects.create(
            name="Поло без остатка",
            category=Product.Category.KNIT,
            price=5000,
            description="Товар закончился",
            image=SimpleUploadedFile(
                "sold-out.png",
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

        response = self.client.get(reverse("collection"))

        self.assertContains(response, "Поло без остатка")
        self.assertContains(response, "НЕТ В НАЛИЧИИ")
        self.assertContains(response, "Под заказ")

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

        collection_response = self.client.get(reverse("collection"))

        self.assertEqual(collection_response.status_code, 200)
        self.assertContains(collection_response, "Пальто")
        self.assertContains(collection_response, "В наличии: 5 шт.")

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
            "category",
            "price",
            "description",
            "image",
            "color",
            "material",
        ):
            self.assertContains(response, f'name="{field}"')
        product_form = response.context["adminform"].form
        self.assertNotIn("sku", product_form.fields)
        self.assertFalse(product_form.fields["material"].required)
        self.assertContains(response, 'name="sizes-0-size"')
        self.assertContains(response, 'name="sizes-0-quantity"')


class AdminUserManagementTests(TestCase):
    def setUp(self):
        self.admin_user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password=get_random_string(40),
        )
        self.client.force_login(self.admin_user)
        self.user_list_url = reverse("admin:auth_user_changelist")

    def test_admin_can_see_registered_users_and_active_sessions(self):
        user = get_user_model().objects.create_user(
            username="customer",
            email="customer@example.com",
            first_name="Айжан",
            password=get_random_string(40),
        )
        CustomerProfile.objects.create(user=user, phone="+996700123456")
        customer_client = Client()
        customer_client.force_login(user)

        response = self.client.get(self.user_list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "customer@example.com")
        self.assertContains(response, "+996700123456")
        self.assertContains(response, "В сети")
        self.assertContains(response, 'value="delete_selected"')
        listed_user = next(
            listed_user
            for listed_user in response.context["cl"].result_list
            if listed_user.pk == user.pk
        )
        self.assertTrue(listed_user.online_status)

    def test_admin_can_block_user_and_end_their_active_sessions(self):
        user = get_user_model().objects.create_user(
            username="customer",
            email="customer@example.com",
            password=get_random_string(40),
        )
        customer_client = Client()
        customer_client.force_login(user)
        session_key = customer_client.session.session_key

        response = self.client.post(
            self.user_list_url,
            {
                "action": "block_users",
                "_selected_action": [str(user.pk)],
                "index": "0",
            },
        )

        self.assertRedirects(response, self.user_list_url)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())


@override_settings(
    TELEGRAM_BOT_TOKEN="test-token",
    TELEGRAM_BOT_USERNAME="status_test_bot",
    TELEGRAM_WEBHOOK_SECRET="test-webhook-secret",
)
class CustomerAccountTests(TestCase):
    def test_customer_must_verify_telegram_contact_before_account_is_created(self):
        registration_page = self.client.get(reverse("register"))
        self.assertEqual(registration_page.status_code, 200)
        self.assertContains(registration_page, "Номер телефона")

        response = self.client.post(
            reverse("register"),
            {
                "phone": "+996 (700) 123-456",
                "first_name": "Айжан Тестова",
                "password1": "STATUS-strong-password-2026!",
                "password2": "STATUS-strong-password-2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://t.me/status_test_bot?start=")
        self.assertFalse(get_user_model().objects.exists())
        pending = PendingPhoneRegistration.objects.get()
        self.assertEqual(pending.phone, "+996700123456")
        self.assertNotEqual(pending.password_hash, "STATUS-strong-password-2026!")

        with (
            patch("PRILOJENIA1.views.send_contact_request") as send_contact_request,
            patch("PRILOJENIA1.views.send_bot_message") as send_bot_message,
        ):
            start_response = self.client.post(
                reverse("telegram_webhook"),
                data=json.dumps({
                    "message": {
                        "chat": {"id": 987, "type": "private"},
                        "from": {"id": 987},
                        "text": f"/start {pending.token}",
                    },
                }),
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-webhook-secret",
            )
            contact_response = self.client.post(
                reverse("telegram_webhook"),
                data=json.dumps({
                    "message": {
                        "chat": {"id": 987, "type": "private"},
                        "from": {"id": 987},
                        "contact": {
                            "user_id": 987,
                            "phone_number": "+996700123456",
                        },
                    },
                }),
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-webhook-secret",
            )

        self.assertEqual(start_response.status_code, 200)
        self.assertTrue(send_contact_request.called)
        self.assertEqual(contact_response.status_code, 200)
        self.assertTrue(send_bot_message.called)
        user = get_user_model().objects.get(username="+996700123456")
        self.assertEqual(user.first_name, "Айжан Тестова")
        self.assertEqual(user.email, "")
        self.assertTrue(user.check_password("STATUS-strong-password-2026!"))
        self.assertTrue(user.customer_profile.phone_verified)

        status_response = self.client.get(reverse("phone_verification_status"))
        self.assertEqual(status_response.json()["status"], "verified")
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_telegram_contact_must_belong_to_the_sender(self):
        response = self.client.post(
            reverse("register"),
            {
                "phone": "+996700123456",
                "first_name": "Айжан",
                "password1": "STATUS-strong-password-2026!",
                "password2": "STATUS-strong-password-2026!",
            },
        )
        pending = PendingPhoneRegistration.objects.get()

        with patch("PRILOJENIA1.views.send_bot_message"):
            webhook_response = self.client.post(
                reverse("telegram_webhook"),
                data=json.dumps({
                    "message": {
                        "chat": {"id": 987, "type": "private"},
                        "from": {"id": 987},
                        "contact": {
                            "user_id": 654,
                            "phone_number": "+996700123456",
                        },
                    },
                }),
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-webhook-secret",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(webhook_response.status_code, 200)
        self.assertFalse(PendingPhoneRegistration.objects.get(pk=pending.pk).user_id)
        self.assertFalse(get_user_model().objects.exists())

    def test_registration_requires_telegram_configuration(self):
        with override_settings(
            TELEGRAM_BOT_TOKEN="",
            TELEGRAM_BOT_USERNAME="",
            TELEGRAM_WEBHOOK_SECRET="",
        ):
            response = self.client.post(
                reverse("register"),
                {
                    "phone": "+996700123456",
                    "first_name": "Айжан",
                    "password1": "STATUS-strong-password-2026!",
                    "password2": "STATUS-strong-password-2026!",
                },
            )

        self.assertContains(response, "Администратору нужно подключить Telegram-бота")
        self.assertEqual(PendingPhoneRegistration.objects.count(), 0)

    def test_telegram_webhook_rejects_requests_without_secret(self):
        response = self.client.post(
            reverse("telegram_webhook"),
            data=json.dumps({"message": {}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)

    def test_existing_unverified_customer_can_verify_their_phone_again(self):
        user = get_user_model().objects.create_user(
            username="old-customer",
            email="old@example.com",
            first_name="Старое имя",
            password="Old-strong-password-2026!",
        )
        CustomerProfile.objects.create(user=user, phone="+996700123456")

        response = self.client.post(
            reverse("register"),
            {
                "phone": "+996700123456",
                "first_name": "Новое имя",
                "password1": "STATUS-strong-password-2026!",
                "password2": "STATUS-strong-password-2026!",
            },
        )
        pending = PendingPhoneRegistration.objects.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(pending.target_user, user)

        with patch("PRILOJENIA1.views.send_bot_message"):
            webhook_response = self.client.post(
                reverse("telegram_webhook"),
                data=json.dumps({
                    "message": {
                        "chat": {"id": 987, "type": "private"},
                        "from": {"id": 987},
                        "contact": {
                            "user_id": 987,
                            "phone_number": "+996700123456",
                        },
                    },
                }),
                content_type="application/json",
                HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="test-webhook-secret",
            )

        self.assertEqual(webhook_response.status_code, 200)
        user.refresh_from_db()
        self.assertEqual(user.username, "+996700123456")
        self.assertEqual(user.first_name, "Новое имя")
        self.assertEqual(user.email, "")
        self.assertTrue(user.customer_profile.phone_verified)
        self.assertTrue(user.check_password("STATUS-strong-password-2026!"))

    def test_customer_can_log_in_with_phone_and_update_profile_name(self):
        user = get_user_model().objects.create_user(
            username="+996700123456",
            email="",
            first_name="Айжан",
            password="STATUS-strong-password-2026!",
        )
        CustomerProfile.objects.create(
            user=user,
            phone="+996700123456",
            phone_verified=True,
        )

        login_page = self.client.get(reverse("login"))
        self.assertEqual(login_page.status_code, 200)
        self.assertContains(login_page, "Номер телефона")

        response = self.client.post(
            reverse("login"),
            {
                "username": "+996700123456",
                "password": "STATUS-strong-password-2026!",
            },
        )
        self.assertRedirects(response, "/")

        response = self.client.post(
            reverse("customer_profile"),
            {
                "first_name": "Айжан Тестова",
            },
        )
        self.assertRedirects(response, reverse("customer_profile"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Айжан Тестова")
        self.assertEqual(user.customer_profile.phone, "+996700123456")

    def test_unverified_phone_cannot_be_used_to_log_in(self):
        user = get_user_model().objects.create_user(
            username="+996700123456",
            email="",
            first_name="Айжан",
            password="STATUS-strong-password-2026!",
        )
        CustomerProfile.objects.create(user=user, phone="+996700123456")

        response = self.client.post(
            reverse("login"),
            {
                "username": "+996700123456",
                "password": "STATUS-strong-password-2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_profile_page_requires_login(self):
        response = self.client.get(reverse("customer_profile"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('customer_profile')}",
        )


class OrderFlowTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        self.override_media = override_settings(MEDIA_ROOT=self.media_dir.name)
        self.override_media.enable()
        self.user = get_user_model().objects.create_user(
            username="customer@example.com",
            email="customer@example.com",
            first_name="Айжан Тестова",
            password="STATUS-strong-password-2026!",
        )
        CustomerProfile.objects.create(
            user=self.user,
            phone="+996700123456",
            phone_verified=True,
        )
        self.product = Product.objects.create(
            name="Поло STATUS",
            category=Product.Category.KNIT,
            price=5000,
            description="Поло",
            image=SimpleUploadedFile(
                "polo.png",
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
        self.size = ProductSize.objects.create(
            product=self.product,
            size="M",
            quantity=3,
        )

    def tearDown(self):
        self.override_media.disable()
        self.media_dir.cleanup()

    def test_order_requires_customer_login(self):
        response = self.client.post(
            reverse("create_order"),
            data=json.dumps({"address": "Бишкек", "items": [{"id": self.product.pk, "quantity": 1}]}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(Order.objects.count(), 0)

    def test_logged_in_customer_order_is_saved_and_stock_is_decreased(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("create_order"),
            data=json.dumps({
                "address": "Бишкек, ул. Токтогула, 1",
                "items": [{"id": self.product.pk, "quantity": 2}],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        order = Order.objects.get()
        self.assertEqual(order.customer_name, "Айжан Тестова")
        self.assertEqual(order.customer_phone, "+996700123456")
        self.assertEqual(order.total_price, 10000)
        self.assertEqual(order.delivery_address, "Бишкек, ул. Токтогула, 1")
        self.assertEqual(OrderItem.objects.get().sizes, "M × 2")
        self.size.refresh_from_db()
        self.assertEqual(self.size.quantity, 1)

    def test_order_rejects_quantity_above_current_stock(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("create_order"),
            data=json.dumps({
                "address": "Бишкек",
                "items": [{"id": self.product.pk, "quantity": 4}],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.size.refresh_from_db()
        self.assertEqual(self.size.quantity, 3)


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

    def test_admin_sidebar_links_to_store_management_sections(self):
        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, "/admin/auth/user/")
        self.assertContains(response, "/admin/PRILOJENIA1/product/add/")
        self.assertContains(response, "/admin/PRILOJENIA1/product/")
        self.assertContains(response, "/admin/PRILOJENIA1/order/")

    def test_admin_can_review_saved_orders(self):
        user = get_user_model().objects.create_user(
            username="customer",
            email="customer@example.com",
            first_name="Айжан Тестова",
            password=get_random_string(40),
        )
        order = Order.objects.create(
            user=user,
            customer_name="Айжан Тестова",
            customer_phone="+996700123456",
            delivery_address="Бишкек",
            total_price=5000,
        )
        OrderItem.objects.create(
            order=order,
            product_name="Поло STATUS",
            quantity=1,
            unit_price=5000,
        )

        response = self.client.get(reverse("admin:PRILOJENIA1_order_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Айжан Тестова")
        self.assertContains(response, "+996700123456")

    def test_add_product_sidebar_item_is_active_without_product_list_active(self):
        response = self.client.get(reverse("admin:PRILOJENIA1_product_add"))
        navigation_items = [
            item
            for group in response.context["sidebar_navigation"]
            for item in group["items"]
        ]
        active_items = {
            item["title"]
            for item in navigation_items
            if item.get("active")
        }

        self.assertIn("Добавить товар", active_items)
        self.assertNotIn("Список товаров", active_items)

    def test_product_list_sidebar_item_is_active_on_product_list(self):
        response = self.client.get(reverse("admin:PRILOJENIA1_product_changelist"))
        navigation_items = [
            item
            for group in response.context["sidebar_navigation"]
            for item in group["items"]
        ]
        active_items = {
            item["title"]
            for item in navigation_items
            if item.get("active")
        }

        self.assertIn("Список товаров", active_items)
        self.assertNotIn("Добавить товар", active_items)

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
