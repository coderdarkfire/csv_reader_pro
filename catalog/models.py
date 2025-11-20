from django.db import models
import uuid


class Product(models.Model):
    sku = models.CharField(max_length=100,unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.sku} - {self.name}"
    
class UploadJob(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    progress = models.IntegerField(default=0)  # 0–100
    message = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)

    def __str__(self):
        return f"UploadJob {self.id} ({self.status})"
    
class Webhook(models.Model):
    EVENT_CHOICES = [
        ("product_created", "Product Created"),
        ("product_updated", "Product Updated"),
        ("product_deleted", "Product Deleted"),
        ("import_completed", "Import Completed"),
    ]

    url = models.URLField()
    event = models.CharField(max_length=100, choices=EVENT_CHOICES)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.url} ({self.event})"