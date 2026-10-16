from django.contrib import admin

from .models import GrammarPattern


@admin.register(GrammarPattern)
class GrammarPatternAdmin(admin.ModelAdmin):
    list_display = ("pattern", "meaning_vi", "level", "category", "display_order")
    list_filter = ("level", "category")
    search_fields = ("pattern", "meaning_vi", "example_jp")
