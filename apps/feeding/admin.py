from django.contrib import admin

from .models import FeedingSchedule


@admin.register(FeedingSchedule)
class FeedingScheduleAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "farm",
        "specie",
        "type",
        "version",
        "is_current",
        "deleted_at",
    )
    list_filter = ("farm", "type", "is_current")
    search_fields = ("name",)
    raw_id_fields = ("farm", "product", "specie", "parent")
