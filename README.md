# STATUS

Интернет-магазин STATUS на Django: каталог с фотографиями, категориями,
ценами и остатками по размерам. Каталог управляется через админ-панель
Django Unfold.

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Откройте сайт на `http://127.0.0.1:8000/`, админ-панель — на
`http://127.0.0.1:8000/admin/`.

Добавляйте товары в админке: укажите цену в сомах, описание и фотографию,
затем добавьте остатки отдельно для каждого размера. Опубликованные товары
появятся в каталоге.

## Секретный ключ

Для постоянной работы и развёртывания задайте переменную окружения
`DJANGO_SECRET_KEY`. Если она не задана, локальный ключ генерируется
автоматически при запуске приложения.

## Развёртывание с Gunicorn

Gunicorn запускает Django WSGI-приложение. Перед запуском задайте
переменные окружения для секретного ключа, режима отладки и домена:

```bash
export DJANGO_SECRET_KEY='ваш-длинный-случайный-секретный-ключ'
export DJANGO_DEBUG=False
export DJANGO_ALLOWED_HOSTS='example.com,www.example.com'
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn STATUS_PROJECT.wsgi:application --bind 0.0.0.0:8000 --workers 3
```

Замените `example.com` на домен сайта. Для локальной разработки используйте
`python manage.py runserver`.

## Проверка

```bash
python manage.py test PRILOJENIA1
python manage.py check
```

Локальная база данных, пользовательские загрузки, виртуальное окружение
и секреты исключены из Git.
