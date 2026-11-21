from django.contrib import admin

from .models import Batch, BatchSource, PondBatch, BatchTransfer


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ["code", "farm", "specie", "biological_state", "status", "created_at"]
    list_filter = ["farm", "status", "biological_state", "created_at"]
    search_fields = ["code", "farm__name", "specie__name"]
    readonly_fields = ["code", "created_at", "updated_at"]
    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "code",
                    "farm",
                    "specie",
                    "origin_type",
                    "origin_id",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "biological_state",
                    "status",
                )
            },
        ),
        (
            "Quantity & Weights",
            {
                "fields": (
                    "initial_quantity",
                    "min_weight_g",
                    "avg_weight_g",
                    "max_weight_g",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "comments",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(BatchSource)
class BatchSourceAdmin(admin.ModelAdmin):
    list_display = ["parent_batch", "child_batch", "quantity"]
    list_filter = ["parent_batch__farm"]
    search_fields = ["parent_batch__code", "child_batch__code"]
    fieldsets = (
        (
            "Genealogy",
            {
                "fields": (
                    "parent_batch",
                    "child_batch",
                    "quantity",
                )
            },
        ),
    )


@admin.register(PondBatch)
class PondBatchAdmin(admin.ModelAdmin):
    list_display = ["batch", "pond", "initial_quantity", "current_quantity", "start_date"]
    list_filter = ["pond__farm", "start_date"]
    search_fields = ["batch__code", "pond__name"]
    readonly_fields = ["start_date"]
    fieldsets = (
        (
            "Assignment",
            {
                "fields": (
                    "pond",
                    "batch",
                )
            },
        ),
        (
            "Quantities",
            {
                "fields": (
                    "initial_quantity",
                    "current_quantity",
                )
            },
        ),
        (
            "Timeline",
            {
                "fields": (
                    "start_date",
                    "end_date",
                )
            },
        ),
    )


@admin.register(BatchTransfer)
class BatchTransferAdmin(admin.ModelAdmin):
    list_display = ["date", "source_pond_batch", "to_pond_batch", "quantity", "farm"]
    list_filter = ["farm", "date"]
    search_fields = ["source_pond_batch__batch__code", "to_pond_batch__batch__code", "reason"]
    fieldsets = (
        (
            "Transfer Details",
            {
                "fields": (
                    "farm",
                    "date",
                    "quantity",
                    "reason",
                )
            },
        ),
        (
            "Ponds",
            {
                "fields": (
                    "source_pond_batch",
                    "to_pond_batch",
                )
            },
        ),
    )
