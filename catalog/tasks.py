import csv
from uuid import UUID
from celery import shared_task
from django.db import transaction
from django.db import connection
from catalog.models import Product, UploadJob


BATCH_SIZE = 5000  # safe for 512MB RAM


@shared_task
def process_product_csv(job_id, file_path):
    job = UploadJob.objects.get(id=UUID(job_id))
    job.status = "PROCESSING"
    job.save(update_fields=["status"])

    total_rows = count_csv_rows(file_path)
    job.total_rows = total_rows
    job.save(update_fields=["total_rows"])

    processed = 0

    try:
        with open(file_path, newline='', encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)

            batch = []
            for row in reader:
                batch.append(row)

                # When batch full → process it
                if len(batch) >= BATCH_SIZE:
                    processed += save_batch(batch)
                    batch = []
                    update_progress(job, processed, total_rows)

            # Process leftover rows
            if batch:
                processed += save_batch(batch)
                update_progress(job, processed, total_rows)

        job.status = "COMPLETED"
        job.progress = 100
        job.save(update_fields=["status", "progress"])

    except Exception as e:
        job.status = "FAILED"
        job.error_message = str(e)
        job.save(update_fields=["status", "error_message"])
        raise


def count_csv_rows(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1  # minus header


def update_progress(job, processed, total):
    progress = int((processed / total) * 100)
    UploadJob.objects.filter(id=job.id).update(progress=progress)


def save_batch(batch_rows):
    """
    Efficient, low-RAM batch save:
    - Convert SKU to lowercase (case-insensitive overwrite)
    - Use bulk UPSERT with PostgreSQL ON CONFLICT
    - Only stores a few thousand rows in memory max
    """

    products = []
    for row in batch_rows:
        products.append(Product(
            sku=row["sku"].strip().lower(),
            name=row.get("name", ""),
            description=row.get("description", ""),
            active=True
        ))

    # BULK UPSERT (overwrite by SKU)
    # Requires PostgreSQL & unique constraint on sku
    with connection.cursor() as cursor:
        cursor.execute("""
            CREATE TEMP TABLE tmp_products (
                sku TEXT,
                name TEXT,
                description TEXT,
                active BOOLEAN
            ) ON COMMIT DROP;
        """)

        # Insert rows into temp table
        args_str = ",".join(
            cursor.mogrify("(%s,%s,%s,%s)", (
                p.sku, p.name, p.description, p.active
            )).decode("utf-8")
            for p in products
        )

        cursor.execute("INSERT INTO tmp_products VALUES " + args_str)

        # Upsert from temp table with ON CONFLICT
        cursor.execute("""
            INSERT INTO catalog_product (sku, name, description, active)
            SELECT sku, name, description, active FROM tmp_products
            ON CONFLICT (sku)
            DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                active = EXCLUDED.active;
        """)

    return len(batch_rows)
