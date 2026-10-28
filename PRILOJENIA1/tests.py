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
    Product,
    ProductSize,
    RestockRequest,
    Store,
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
        self.store = Store.objects.create(
            name="Токтогула",
            address="ул. Токтогула, 87",
            is_default=True,
        )

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
        self.assertContains(response, "КОЛЛЕКЦИЯ")
        self.assertContains(response, 'data-filter="knit"')
        self.assertContains(response, "Коллекция скоро появится")
        self.assertContains(response, "Токтогула")

    def test_products_sold_out_everywhere_move_to_out_of_stock_page(self):
        product = Product.objects.create(
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
        ProductSize.objects.create(
            product=product,
            store=self.store,
            size="M",
            quantity=0,
        )

        collection_response = self.client.get(reverse("collection"))

        self.assertNotContains(collection_response, "Поло без остатка")

        stock_response = self.client.get(reverse("out_of_stock"))

        self.assertEqual(stock_response.status_code, 200)
        self.assertContains(stock_response, "Поло без остатка")

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
        ProductSize.objects.create(
            product=product, store=self.store, size="M", quantity=3
        )
        ProductSize.objects.create(
            product=product, store=self.store, size="L", quantity=2
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["products"][0]["name"], product.name)
        self.assertEqual(response.context["products"][0]["sizes"], [
            {"size": "M", "quantity": 3},
            {"size": "L", "quantity": 2},
        ])
        self.assertEqual(response.context["products"][0]["totalStock"], 5)
        self.assertContains(response, "/media/products/coat.png")

        collection_response = self.client.get(reverse("collection"))

        self.assertEqual(collection_response.status_code, 200)
        self.assertContains(collection_response, "Пальто")
        self.assertEqual(
            collection_response.context["catalog"][0]["total_stock"], 5
        )

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


class CustomerAccountTests(TestCase):
    def test_customer_can_register_without_phone_verification_and_is_logged_in(self):
        registration_page = self.client.get(reverse("register"))
        self.assertEqual(registration_page.status_code, 200)
        self.assertContains(registration_page, "Номер телефона")
        self.assertNotContains(registration_page, "Telegram")

        response = self.client.post(
            reverse("register"),
            {
                "phone": "+996 (700) 123-456",
                "first_name": "Айжан Тестова",
                "password1": "STATUS-strong-password-2026!",
                "password2": "STATUS-strong-password-2026!",
            },
        )

        user = get_user_model().objects.get(username="+996700123456")
        self.assertRedirects(response, reverse("customer_profile"))
        self.assertEqual(user.first_name, "Айжан Тестова")
        self.assertEqual(user.email, "")
        self.assertTrue(user.check_password("STATUS-strong-password-2026!"))
        self.assertEqual(user.customer_profile.phone, "+996700123456")
        self.assertEqual(int(self.client.session[SESSION_KEY]), user.pk)

    def test_registration_rejects_a_phone_already_in_use(self):
        user = get_user_model().objects.create_user(
            username="+996700123456",
            first_name="Существующий покупатель",
            password="STATUS-strong-password-2026!",
        )
        CustomerProfile.objects.create(user=user, phone="+996700123456")

        response = self.client.post(
            reverse("register"),
            {
                "phone": "+996700123456",
                "first_name": "Другой человек",
                "password1": "STATUS-another-strong-password-2026!",
                "password2": "STATUS-another-strong-password-2026!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "уже зарегистрирован")
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_customer_can_log_in_with_phone_and_update_profile_name(self):
        user = get_user_model().objects.create_user(
            username="legacy-customer",
            email="",
            first_name="Айжан",
            password="STATUS-strong-password-2026!",
        )
        CustomerProfile.objects.create(user=user, phone="+996700123456")

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
            {"first_name": "Айжан Тестова"},
        )
        self.assertRedirects(response, reverse("customer_profile"))
        user.refresh_from_db()
        self.assertEqual(user.first_name, "Айжан Тестова")
        self.assertEqual(user.customer_profile.phone, "+996700123456")

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
        )
        self.store = Store.objects.create(
            name="Токтогула",
            address="ул. Токтогула, 87",
            is_default=True,
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
            store=self.store,
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

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(len(response.json()["conflicts"]), 1)
        self.size.refresh_from_db()
        self.assertEqual(self.size.quantity, 3)

    def test_cart_orders_tab_shows_only_customer_orders_and_their_statuses(self):
        for status in (
            Order.Status.PROCESSING,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        ):
            order = Order.objects.create(
                user=self.user,
                customer_name="Айжан Тестова",
                customer_phone="+996700123456",
                delivery_address="Бишкек",
                total_price=5000,
                status=status,
            )
            OrderItem.objects.create(
                order=order,
                product_name=f"Товар {status}",
                quantity=1,
                unit_price=5000,
            )

        another_user = get_user_model().objects.create_user(
            username="another-customer",
            password="another-strong-password",
        )
        Order.objects.create(
            user=another_user,
            customer_name="Другой покупатель",
            customer_phone="+996555000000",
            delivery_address="Ош",
            total_price=9000,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Мои заказы")
        self.assertContains(response, "В обработке")
        self.assertContains(response, "Выполнен")
        self.assertContains(response, "Отменён")
        self.assertNotContains(response, "Другой покупатель")
        self.assertEqual(len(response.context["customer_orders"]), 3)

    def test_guest_can_open_orders_tab_and_is_asked_to_sign_in(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Мои заказы")
        self.assertContains(response, "Войдите, чтобы увидеть заказы")
        self.assertContains(response, "Войти в аккаунт")


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


class StoreStockTests(TestCase):
    def setUp(self):
        self.main = Store.objects.create(
            name="Токтогула", address="ул. Токтогула, 87", is_default=True
        )
        self.second = Store.objects.create(name="Чуй", address="пр. Чуй, 155")
        self.product = Product.objects.create(
            name="Поло «Borgona»",
            sku="ST-KN-104",
            category=Product.Category.KNIT,
            price=18400,
            description="Тест",
            image="products/polo.jpg",
        )
        self.sold_out = Product.objects.create(
            name="Кашне «Como»",
            sku="ST-AC-512",
            category=Product.Category.ACCESSORIES,
            price=9200,
            description="Тест",
            image="products/scarf.jpg",
        )
        ProductSize.objects.create(
            product=self.product, store=self.main, size="M", quantity=1
        )
        ProductSize.objects.create(
            product=self.product, store=self.second, size="L", quantity=4
        )
        ProductSize.objects.create(
            product=self.sold_out, store=self.main, size="ONE SIZE", quantity=0
        )
        ProductSize.objects.create(
            product=self.sold_out, store=self.second, size="ONE SIZE", quantity=0
        )

    def test_store_selection_is_kept_in_session(self):
        response = self.client.post(
            reverse("select_store"),
            {"store": self.second.pk, "next": reverse("collection")},
        )

        self.assertRedirects(response, reverse("collection"))
        self.assertEqual(self.client.session["store_id"], self.second.pk)

    def test_store_selection_ignores_foreign_redirect(self):
        response = self.client.post(
            reverse("select_store"),
            {"store": self.second.pk, "next": "https://evil.example.com/"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example.com", response["Location"])

    def test_default_store_is_used_for_first_visit(self):
        response = self.client.get(reverse("collection"))

        self.assertEqual(response.context["current_store"], self.main)

    def test_catalog_shows_stock_of_selected_store_only(self):
        response = self.client.get(reverse("collection"))

        items = {item["product"].pk: item for item in response.context["catalog"]}
        self.assertEqual(items[self.product.pk]["total_stock"], 1)
        self.assertEqual(
            [stock.size for stock in items[self.product.pk]["sizes"]], ["M"]
        )
        self.assertEqual(
            items[self.product.pk]["other_stores"][0]["store"], self.second
        )

    def test_sold_out_products_are_not_in_catalog(self):
        response = self.client.get(reverse("collection"))

        products = [item["product"].pk for item in response.context["catalog"]]
        self.assertNotIn(self.sold_out.pk, products)

    def test_out_of_stock_page_lists_only_sold_out_products(self):
        response = self.client.get(reverse("out_of_stock"))

        products = [item["product"].pk for item in response.context["items"]]
        self.assertEqual(products, [self.sold_out.pk])

    def _customer(self, username="+996700000001"):
        user = get_user_model().objects.create_user(
            username=username, first_name="Тест", password="Secret12345"
        )
        CustomerProfile.objects.create(user=user, phone=username)
        self.client.force_login(user)
        return user

    def _checkout(self, items, **extra):
        payload = {"address": "г. Бишкек, ул. Киевская 1", "items": items}
        payload.update(extra)
        return self.client.post(
            reverse("create_order"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_cart_validate_marks_short_and_gone_lines(self):
        response = self.client.post(
            reverse("validate_cart"),
            data=json.dumps(
                {
                    "items": [
                        {"id": self.product.pk, "store": self.main.pk, "quantity": 3},
                        {"id": self.sold_out.pk, "store": self.main.pk, "quantity": 1},
                    ]
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        lines = {
            (line["product_id"], line["store_id"]): line
            for line in response.json()["lines"]
        }
        short_line = lines[(self.product.pk, self.main.pk)]
        self.assertEqual(short_line["status"], "short")
        self.assertEqual(short_line["available"], 1)
        self.assertEqual(short_line["others"][0]["store_name"], "Чуй")
        self.assertEqual(lines[(self.sold_out.pk, self.main.pk)]["status"], "gone")

    def test_checkout_splits_lines_into_one_order_per_store(self):
        self._customer()
        response = self._checkout(
            [
                {"id": self.product.pk, "store": self.main.pk, "quantity": 1},
                {"id": self.product.pk, "store": self.second.pk, "quantity": 2},
            ],
            checkout_id="11111111-1111-4111-8111-111111111111",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["orders"]), 2)
        orders = list(Order.objects.order_by("store_id"))
        self.assertEqual(
            {order.store_id for order in orders}, {self.main.pk, self.second.pk}
        )
        self.assertEqual(len({str(order.checkout_id) for order in orders}), 1)
        self.assertEqual(
            ProductSize.objects.get(
                product=self.product, store=self.main, size="M"
            ).quantity,
            0,
        )
        self.assertEqual(
            ProductSize.objects.get(
                product=self.product, store=self.second, size="L"
            ).quantity,
            2,
        )

    def test_checkout_with_conflicts_creates_nothing(self):
        self._customer()
        response = self._checkout(
            [{"id": self.product.pk, "store": self.main.pk, "quantity": 3}],
            checkout_id="22222222-2222-4222-8222-222222222222",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["conflicts"][0]["available"], 1)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(
            ProductSize.objects.get(
                product=self.product, store=self.main, size="M"
            ).quantity,
            1,
        )

    def test_checkout_confirm_partial_keeps_only_available_lines(self):
        self._customer()
        response = self._checkout(
            [
                {"id": self.product.pk, "store": self.main.pk, "quantity": 1},
                {"id": self.sold_out.pk, "store": self.main.pk, "quantity": 1},
            ],
            confirm_partial=True,
            checkout_id="33333333-3333-4333-8333-333333333333",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["orders"]), 1)
        self.assertEqual(len(data["dropped"]), 1)
        self.assertEqual(OrderItem.objects.count(), 1)

    def test_checkout_duplicate_checkout_id_is_idempotent(self):
        self._customer()
        items = [{"id": self.product.pk, "store": self.main.pk, "quantity": 1}]
        first = self._checkout(
            items, checkout_id="44444444-4444-4444-8444-444444444444"
        )
        second = self._checkout(
            items, checkout_id="44444444-4444-4444-8444-444444444444"
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(Order.objects.count(), 1)

    def test_checkout_is_atomic_when_another_store_lacks_stock(self):
        self._customer()
        response = self._checkout(
            [
                {"id": self.product.pk, "store": self.second.pk, "quantity": 4},
                {"id": self.product.pk, "store": self.main.pk, "quantity": 5},
            ]
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(
            ProductSize.objects.get(
                product=self.product, store=self.second, size="L"
            ).quantity,
            4,
        )

    def test_restock_request_is_created_from_sold_out_page(self):
        response = self.client.post(
            reverse("out_of_stock"),
            {
                "product": self.sold_out.pk,
                "kind": RestockRequest.Kind.TAILOR,
                "phone": "+996700000003",
                "comment": "Нужен размер",
            },
        )

        self.assertEqual(response.status_code, 302)
        restock_request = RestockRequest.objects.get()
        self.assertEqual(restock_request.product, self.sold_out)
        self.assertEqual(restock_request.kind, RestockRequest.Kind.TAILOR)

    def test_checkout_rejects_quantity_above_selected_store_stock(self):
        user = get_user_model().objects.create_user(
            username="+996700000004", first_name="Тест", password="Secret12345"
        )
        CustomerProfile.objects.create(user=user, phone="+996700000004")
        self.client.force_login(user)
        self.client.post(reverse("select_store"), {"store": self.main.pk})

        response = self.client.post(
            reverse("create_order"),
            data=json.dumps(
                {
                    "address": "г. Бишкек, ул. Киевская 1",
                    "items": [{"id": self.product.pk, "quantity": 2}],
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["conflicts"][0]["store_name"], "Токтогула")
        self.assertEqual(Order.objects.count(), 0)
