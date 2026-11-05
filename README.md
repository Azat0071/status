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

## Совместная работа через GitHub

Обе рабочие копии должны быть клонами одного репозитория. Перед началом
работы каждый разработчик получает последние изменения:

```bash
git switch main
git pull --ff-only origin main
```

После своих изменений разработчик сохраняет и отправляет их:

```bash
git add <изменённые-файлы>
git commit -m "Кратко описать изменения"
git push origin main
```

После этого второй разработчик выполняет `git pull --ff-only origin main`.
Сначала отправляет изменения один человек, затем второй забирает их перед
продолжением работы. Не используйте `git push --force` для общей ветки.

Изменения кода не появляются в браузере другого разработчика автоматически:
их нужно отправить в GitHub, получить через `git pull` и перезапустить свой
локальный сервер при необходимости. Адрес `localhost` у каждого ведёт на его
собственный компьютер. Локальная SQLite-база (`db.sqlite3`), товары и заказы
через Git не синхронизируются; для общих данных нужна общая dev-база данных.

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
