from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "ui_theme", "is_active", "date_joined")
    list_filter = ("ui_theme", "is_active")
