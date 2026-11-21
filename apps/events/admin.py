from django.contrib import admin

from .models import GradingEvent


@admin.register(GradingEvent)
class GradingEventAdmin(admin.ModelAdmin):
    list_display = ["date", "cycle", "quantity", "source_pond_batch", "to_pond_batch"]
    list_filter = ["cycle__farm", "date"]
    search_fields = ["cycle__name", "source_pond_batch__batch__code", "to_pond_batch__batch__code"]
    fieldsets = (
        (
            "Event Details",
            {
                "fields": (
                    "cycle",
                    "date",
                    "quantity",
                )
            },
        ),
        (
            "Transfer",
            {
                "fields": (
                    "source_pond_batch",
                    "to_pond_batch",
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
