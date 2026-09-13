from django.contrib import admin

from apps.core.models import MasterCode


@admin.register(MasterCode)
class MasterCodeAdmin(admin.ModelAdmin):
    list_display = ("code_type", "code", "code_name", "mother_code", "sort_order", "is_active")
    list_filter = ("code_type", "is_active")
    search_fields = ("code", "code_name", "description")
    ordering = ("code_type", "sort_order", "code")
