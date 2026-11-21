from django.contrib import admin

from .models import ProductionPlan, Cycle, CyclePondBatch


@admin.register(ProductionPlan)
class ProductionPlanAdmin(admin.ModelAdmin):
    list_display = ["name", "farm", "specie", "type", "version", "is_current", "created_at"]
    list_filter = ["farm", "type", "is_current", "created_at"]
    search_fields = ["name", "farm__name", "specie__name"]
    readonly_fields = ["version", "created_at", "updated_at"]
    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "farm",
                    "specie",
                    "name",
                    "type",
                )
            },
        ),
        (
            "Parameters",
            {
                "fields": (
                    "total_days",
                    "expected_mortality_rate",
                    "expected_final_weight",
                    "expected_reproduction_rate",
                )
            },
        ),
        (
            "Versioning",
            {
                "fields": (
                    "version",
                    "is_current",
                    "parent",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "deleted_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Cycle)
class CycleAdmin(admin.ModelAdmin):
    list_display = ["name", "farm", "specie", "state", "start_date", "estimated_finish_date"]
    list_filter = ["farm", "state", "start_date"]
    search_fields = ["name", "farm__name", "specie__name"]
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (
            "Basic Info",
            {
                "fields": (
                    "farm",
                    "specie",
                    "pond",
                    "production_plan",
                    "name",
                )
            },
        ),
        (
            "Status & Dates",
            {
                "fields": (
                    "state",
                    "start_date",
                    "estimated_finish_date",
                    "finish_date",
                )
            },
        ),
        (
            "Weights",
            {
                "fields": (
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
                    "deleted_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(CyclePondBatch)
class CyclePondBatchAdmin(admin.ModelAdmin):
    list_display = ["cycle", "pond_batch", "quantity"]
    list_filter = ["cycle__farm"]
    search_fields = ["cycle__name", "pond_batch__batch__code"]
    fieldsets = (
        (
            "Assignment",
            {
                "fields": (
                    "cycle",
                    "pond_batch",
                    "quantity",
                )
            },
        ),
        (
            "Weights",
            {
                "fields": (
                    "min_weight_g",
                    "avg_weight_g",
                    "max_weight_g",
                )
            },
        ),
    )
