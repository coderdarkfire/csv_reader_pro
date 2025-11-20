import csv
from uuid import UUID
from pathlib import Path
from celery import shared_task
from django.db import transaction
from .models import Product, UploadJob


BATCH_SIZE = 5000   # optimal for PostgreSQL


@shared_task
def process_product_csv(job_id, file_path):
    job = UploadJob.objects.get(id=UUID(job_id))
    job.status = "processing"
    job.progress = 0
    job.message = "Starting import..."
    job.save()

    path = Path(file_path)
    if not path.exists():
        job.status = "failed"
        job.error = f"File not found: {file_path}"
        job.save()
        return

    try:
        # ------------------------
        # 1. Load all existing SKUs once (case-insensitive)
        # ------------------------
        job.message = "Loading existing products..."
        job.save()

        existing_products = Product.objects.all().values("id", "sku")
        existing_map = {p["sku"].lower(): p["id"] for p in existing_products}

        total_existing = len(existing_map)

        # ------------------------
        # 2. Prepare bulk buffers
        # ------------------------
        to_create = []
        to_update = []

        processed = 0

        # ------------------------
        # 3. Stream CSV once
        # ------------------------
        with path.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        total_rows = len(rows)
        if total_rows == 0:
            job.status = "failed"
            job.error = "CSV file is empty."
            job.save()
            return

        # ------------------------
        # 4. Process rows in memory
        # ------------------------
        for row in rows:
            sku_raw = (row.get("sku") or "").strip()
            if not sku_raw:
                continue

            name = (row.get("name") or "").strip()
            description = (row.get("description") or "").strip()

            sku_key = sku_raw.lower()

            if sku_key in existing_map:
                # Existing → prepare update
                to_update.append(
                    Product(
                        id=existing_map[sku_key],
                        sku=sku_raw,
                        name=name,
                        description=description,
                        active=True,
                    )
                )
            else:
                # New product → prepare create
                to_create.append(
                    Product(
                        sku=sku_raw,
                        name=name,
                        description=description,
                        active=True,
                    )
                )

            processed += 1

            # ------------------------
            # Batch commit + progress
            # ------------------------
            if processed % BATCH_SIZE == 0:
                _bulk_apply(to_create, to_update)
                to_create = []
                to_update = []

                progress = int((processed / total_rows) * 100)
                job.progress = progress
                job.message = f"Processed {processed}/{total_rows} rows..."
                job.save()

        # ------------------------
        # 5. Final batch commit
        # ------------------------
        _bulk_apply(to_create, to_update)

        job.status = "completed"
        job.progress = 100
        job.message = (
            f"Import complete. {processed} rows processed. "
            f"{len(to_create)} new, {len(to_update)} updated."
        )
        job.save()

    except Exception as e:
        job.status = "failed"
        job.error = str(e)
        job.save()


def _bulk_apply(to_create, to_update):
    """
    Helper to apply bulk inserts and updates efficiently.
    """
    if to_create:
        Product.objects.bulk_create(to_create, ignore_conflicts=True)

    if to_update:
        # bulk_update requires a list of fields
        Product.objects.bulk_update(
            to_update, ["name", "description", "active"]
        )
