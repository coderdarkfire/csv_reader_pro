import os
import uuid
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Product
from .models import UploadJob
from .tasks import process_product_csv
from django.contrib import messages

@require_http_methods(["GET", "POST"])
def upload_products_view(request):
    if request.method == "POST":
        file = request.FILES.get('file')
        if not file:
            return render(request, 'catalog/upload.html', {
                'error': 'Please select a CSV file.'
            })

        # Save file to media/uploads
        upload_dir = settings.MEDIA_ROOT / 'uploads'
        os.makedirs(upload_dir, exist_ok=True)

        file_name = f"products_{uuid.uuid4()}.csv"
        file_path = upload_dir / file_name

        with open(file_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)

        # Create UploadJob
        job = UploadJob.objects.create(
            status="pending",
            progress=0,
            message="Queued for processing..."
        )

        # Trigger Celery task
        process_product_csv.delay(str(job.id), str(file_path))

        # Redirect to progress page
        return redirect('catalog:upload_progress', job_id=job.id)

    return render(request, 'catalog/upload.html')


def upload_progress_view(request, job_id):
    job = get_object_or_404(UploadJob, id=job_id)
    return render(request, 'catalog/upload_progress.html', {'job': job})


def upload_status_api(request, job_id):
    job = get_object_or_404(UploadJob, id=job_id)
    data = {
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "error": job.error,
    }
    return JsonResponse(data)

def product_list(request):
    query = request.GET.get("q", "")
    sku = request.GET.get("sku", "")
    active = request.GET.get("active", "")
    
    products = Product.objects.all()

    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query)
        )

    if sku:
        products = products.filter(sku__icontains=sku)

    if active == "true":
        products = products.filter(active=True)
    elif active == "false":
        products = products.filter(active=False)

    paginator = Paginator(products, 25)  # 25 rows per page
    page = request.GET.get("page")
    paginated_products = paginator.get_page(page)

    return render(request, "catalog/product_list.html", {
        "products": paginated_products,
        "query": query,
        "sku": sku,
        "active_filter": active
    })
    
def product_create(request):
    if request.method == "POST":
        sku = request.POST["sku"]
        name = request.POST["name"]
        description = request.POST["description"]
        active = bool(request.POST.get("active"))

        Product.objects.create(
            sku=sku,
            name=name,
            description=description,
            active=active
        )
        return redirect("catalog:product_list")

    return render(request, "catalog/product_form.html")


def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)

    if request.method == "POST":
        product.sku = request.POST["sku"]
        product.name = request.POST["name"]
        product.description = request.POST["description"]
        product.active = bool(request.POST.get("active"))
        product.save()
        return redirect("catalog:product_list")

    return render(request, "catalog/product_form.html", {"product": product})

def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    return redirect("catalog:product_list")

def product_delete_all(request):
    if request.method == "POST":
        Product.objects.all().delete()
        messages.success(request, "All products have been deleted successfully.")
        return redirect("catalog:product_list")

    return redirect("catalog:product_list")