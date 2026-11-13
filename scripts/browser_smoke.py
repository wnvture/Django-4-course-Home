"""CI-only browser regression against a disposable database; no external accounts."""

import os
import sys
import tempfile
from pathlib import Path
from threading import Thread
from wsgiref.simple_server import make_server

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "app.settings")

import django
from django.conf import settings

work = tempfile.TemporaryDirectory(prefix="home-browser-")
settings.DATABASES["default"]["NAME"] = Path(work.name) / "browser.sqlite3"
settings.MEDIA_ROOT = Path(work.name) / "media"
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
settings.DEBUG = True
settings.SECURE_SSL_REDIRECT = False
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
django.setup()

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from playwright.sync_api import expect, sync_playwright
from goods.models import Products
from orders.models import Order
from users.models import User

artifacts = ROOT / "outputs/browser"
artifacts.mkdir(parents=True, exist_ok=True)
call_command("migrate", verbosity=0, interactive=False)
call_command("seed_demo", verbosity=0)
# This account exists only inside the disposable test database.
User.objects.create_user(
    username="smoke-manager", password="Demo!Furniture4820", is_staff=True
)
server = make_server("127.0.0.1", 0, StaticFilesHandler(get_wsgi_application()))
thread = Thread(target=server.serve_forever, daemon=True)
thread.start()
base = f"http://127.0.0.1:{server.server_port}"
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(base)
            expect(page.get_by_role("heading", level=1)).to_contain_text(
                "Дом начинается"
            )
            page.screenshot(path=str(artifacts / "home-desktop.png"), full_page=True)
            expect(page.locator("img")).not_to_have_count(0)
            assert page.locator("img").evaluate_all(
                "(images) => images.every(i => i.complete && i.naturalWidth > 0)"
            ), "Broken product image"
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(artifacts / "home-mobile.png"), full_page=True)
            assert page.evaluate(
                "document.documentElement.scrollWidth <= window.innerWidth"
            ), "Mobile page overflows"
            page.set_viewport_size({"width": 1440, "height": 1000})
            first = Products.objects.filter(quantity__gt=0).first()
            initial_stock = first.quantity
            page.goto(base + first.get_absolute_url())
            page.get_by_role("button", name="Добавить в корзину").click()
            page.goto(base + "/user/registration/")
            for name, value in {
                "first_name": "Тест",
                "last_name": "Покупатель",
                "username": "smoke-buyer",
                "email": "buyer@example.com",
                "password1": "Demo!Furniture4820",
                "password2": "Demo!Furniture4820",
            }.items():
                page.locator(f'[name="{name}"]').fill(value)
            page.get_by_role("button", name="Создать аккаунт").click()
            expect(page).to_have_url(base + "/user/profile/")
            page.goto(base + "/orders/create-order/")
            page.locator('[name="phone_number"]').fill("+7 700 123 45 67")
            page.get_by_label("Доставка", exact=True).check()
            expect(page.locator('[name="delivery_address"]')).to_be_visible()
            page.locator('[name="delivery_address"]').fill("Учебный адрес, 1")
            page.screenshot(path=str(artifacts / "checkout.png"), full_page=True)
            page.get_by_role("button", name="Подтвердить учебный заказ").click()
            expect(page).to_have_url(base + "/user/profile/")
            expect(page.get_by_text("Заказ № 1", exact=True)).to_be_visible()
            assert Order.objects.count() == 1
            first.refresh_from_db()
            assert first.quantity == initial_stock - 1
            page.get_by_role("button", name="Выйти", exact=True).click()
            page.goto(base + "/user/login/")
            page.locator('[name="username"]').fill("smoke-manager")
            page.locator('[name="password"]').fill("Demo!Furniture4820")
            page.get_by_role("button", name="Войти").click()
            page.goto(base + "/inventory/")
            page.locator('[name="file"]').set_input_files(
                str(ROOT / "examples/products.csv")
            )
            page.get_by_role("button", name="Проверить CSV").click()
            expect(
                page.get_by_role("heading", name="Предпросмотр импорта.")
            ).to_be_visible()
            assert not Products.objects.filter(sku="OFFICE-CHAIR-001").exists()
            page.get_by_role("button", name="Применить 2 строк").click()
            expect(
                page.get_by_role("heading", name="Остатки и товары.")
            ).to_be_visible()
            assert Products.objects.filter(sku="OFFICE-CHAIR-001", quantity=10).exists()
            page.screenshot(path=str(artifacts / "inventory.png"), full_page=True)
            assert not errors, errors
            print(
                "Browser smoke passed: responsive pages, guest cart → registration → checkout, staff CSV preview → apply, no JS errors."
            )
        except Exception:
            page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
            raise
        finally:
            browser.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
    work.cleanup()
