from django.contrib import admin
from .models import Product, UploadJob

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'active')
    search_fields = ('sku', 'name', 'description')
    list_filter = ('active',)

@admin.register(UploadJob)
class UploadJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'progress', 'created_at', 'message')
    readonly_fields = ('id', 'created_at')