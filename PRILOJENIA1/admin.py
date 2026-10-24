from django.contrib import admin
from django.db.models import Sum
from django.db.models.functions import Coalesce
from unfold.admin import ModelAdmin, TabularInline

from .models import Product, ProductSize


class ProductSizeInline(TabularInline):
    model = ProductSize
    extra = 2
    fields = ("size", "quantity")
    verbose_name = "Размер и остаток"
    verbose_name_plural = "Остатки на складе по размерам"


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = (
        "name",
        "category",
        "price",
        "total_stock",
        "is_available",
        "created_at",
    )
    list_filter = ("category", "is_available")
    search_fields = ("name", "sku", "description", "material", "color")
    list_editable = ("is_available",)
    list_per_page = 25
    inlines = (ProductSizeInline,)
    fieldsets = (
        ("Основная информация", {
            "fields": ("name", "sku", "category", "description"),
        }),
        ("Цена и фотографии", {
            "fields": ("price", "image"),
        }),
        ("Характеристики", {
            "fields": ("color", "material"),
        }),
        ("Публикация", {
            "fields": ("is_available", "created_at"),
        }),
    )
    readonly_fields = ("created_at",)

    @admin.display(description="Всего на складе", ordering="stock_total")
    def total_stock(self, obj):
        return obj.stock_total

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            stock_total=Coalesce(Sum("sizes__quantity"), 0)
        )
