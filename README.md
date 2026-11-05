# STATUS

Интернет-магазин STATUS на Django: каталог, оформление заказа, остатки по
размерам и панель управления для продажи одежды в атмосфере premium.
Проект настроен так, чтобы его можно было быстро запускать локально и
безопасно развёртывать в продакшене.

## Быстрый старт локально

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap_admin
python manage.py seed_demo_catalog
python manage.py runserver 0.0.0.0:8000
```

Откройте сайт на `http://127.0.0.1:8000/`, админ-панель — на
`http://127.0.0.1:8000/admin/`.

## Переменные окружения

Создайте файл `.env` на основе шаблона `.env.example` и задайте:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `ADMIN_USERNAME` и `ADMIN_PASSWORD`
- `ADMIN_EMAIL` (по желанию)
- `DATABASE_URL` (для PostgreSQL в продакшене, например `postgres://user:pass@host:5432/dbname`)
- `CSRF_TRUSTED_ORIGINS` для продакшена

Если переменные не заданы, проект использует безопасный локальный ключ и SQLite.

## Продакшн и Render

Команда запуска `./start.sh` сохранена в `render.yaml`. Скрипт:

1. применяет миграции,
2. создаёт администратора из `ADMIN_*`,
3. собирает статические файлы,
4. инициализирует демо-каталог, если товаров ещё нет,
5. запускает Gunicorn.

Для Render задайте:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=False`
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD`
- `ADMIN_EMAIL` (по желанию)
- `DATABASE_URL` (если используете PostgreSQL)

## База данных

Локально проект работает на SQLite. Для продажной среды рекомендуется PostgreSQL:

```bash
export DATABASE_URL="postgresql://user:password@host:5432/status"
python manage.py migrate
python manage.py collectstatic --noinput
```

## Проверка качества

```bash
python manage.py test PRILOJENIA1
python manage.py check
```

Итог: магазин уже настроен под продажу, а демо-каталог хранит товарные позиции,
остатки и точки продаж, которые легко заменить на реальные данные.
