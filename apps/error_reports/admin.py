from django.contrib import admin

from .models import ErrorReport


@admin.register(ErrorReport)
class ErrorReportAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "vocabulary", "error_type_code", "status_code", "created_at", "handled_by")
    list_filter = ("error_type_code", "status_code")
    search_fields = ("description", "suggested_fix", "user__username", "vocabulary__word")
