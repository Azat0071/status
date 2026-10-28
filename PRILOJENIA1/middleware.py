"""Определение точки продаж, выбранной покупателем."""

from .models import Store

SESSION_KEY = "store_id"


class CurrentStoreMiddleware:
    """Кладёт в request.store активную точку продаж.

    Точка берётся из сессии, иначе используется точка по умолчанию.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.store = self._resolve_store(request)
        return self.get_response(request)

    @staticmethod
    def _resolve_store(request):
        store_id = request.session.get(SESSION_KEY)
        if store_id is not None:
            store = Store.objects.filter(pk=store_id, is_active=True).first()
            if store is not None:
                return store
            request.session.pop(SESSION_KEY, None)
        return Store.default()


def select_store(request, store):
    """Запоминает точку в сессии и в текущем запросе."""
    request.session[SESSION_KEY] = store.pk
    request.store = store
