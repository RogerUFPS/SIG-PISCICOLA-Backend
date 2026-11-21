from django.contrib import admin

from .models import FishEvaluated, DailyStat, ProductUsageLog, ControlStat


@admin.register(FishEvaluated)
class FishEvaluatedAdmin(admin.ModelAdmin):
    list_display = ["id", "cycle", "pond", "evaluation_date", "sampled_quantity", "created_at"]
    list_filter = ["evaluation_date", "cycle", "pond"]
    search_fields = ["cycle__name", "pond__name"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]
    date_hierarchy = "evaluation_date"


@admin.register(DailyStat)
class DailyStatAdmin(admin.ModelAdmin):
    list_display = ["id", "cycle", "pond", "stat_date", "name", "created_at"]
    list_filter = ["stat_date", "cycle", "pond"]
    search_fields = ["cycle__name", "pond__name", "name"]
    readonly_fields = ["created_at", "updated_at", "deleted_at"]
    date_hierarchy = "stat_date"


@admin.register(ProductUsageLog)
class ProductUsageLogAdmin(admin.ModelAdmin):
    list_display = ["id", "daily_stat", "product", "quantity_used", "unit", "batch", "created_at"]
    list_filter = ["unit", "created_at", "product"]
    search_fields = ["product__name", "batch__code", "daily_stat__name"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "created_at"


@admin.register(ControlStat)
class ControlStatAdmin(admin.ModelAdmin):
    list_display = ["id", "cycle", "pond", "control_date", "live_quantity", "biomass_kg", "created_at"]
    list_filter = ["control_date", "cycle", "pond"]
    search_fields = ["cycle__name", "pond__name"]
    readonly_fields = [
        "created_at", "updated_at", "deleted_at", "sampled_quantity", "live_quantity",
        "min_weight_g", "avg_weight_g", "max_weight_g", "mortality_percentage",
        "biomass_kg", "fca", "biomass_gain_kg"
    ]
    date_hierarchy = "control_date"
