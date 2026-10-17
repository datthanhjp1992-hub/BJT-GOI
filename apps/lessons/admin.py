from django.contrib import admin

from .models import (
    Drill,
    DrillItem,
    Lesson,
    PolitenessPhrase,
    Roleplay,
    RoleplayBlank,
    RoleplayLine,
    Unit,
    UserPracticeMark,
)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("number", "name_jp", "name_vi")


class PolitenessPhraseInline(admin.TabularInline):
    model = PolitenessPhrase
    extra = 0
    fields = ("phrase_jp", "level_code")


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ("scene_no", "title_jp", "title_vi", "unit")
    list_filter = ("unit",)
    search_fields = ("title_jp", "title_vi")
    inlines = [PolitenessPhraseInline]


class DrillItemInline(admin.TabularInline):
    model = DrillItem
    extra = 0
    fields = ("number", "prompt_jp", "answer_jp")


@admin.register(Drill)
class DrillAdmin(admin.ModelAdmin):
    list_display = ("lesson", "example_prompt_jp", "example_answer_jp")
    search_fields = ("example_prompt_jp", "example_answer_jp", "items__answer_jp")
    inlines = [DrillItemInline]


class RoleplayLineInline(admin.TabularInline):
    model = RoleplayLine
    extra = 0
    fields = ("number", "speaker", "text_jp")


class RoleplayBlankInline(admin.TabularInline):
    model = RoleplayBlank
    extra = 0
    fields = ("number", "answer_jp")


@admin.register(Roleplay)
class RoleplayAdmin(admin.ModelAdmin):
    list_display = ("unit", "number", "book_page")
    list_filter = ("unit",)
    inlines = [RoleplayLineInline, RoleplayBlankInline]


@admin.register(PolitenessPhrase)
class PolitenessPhraseAdmin(admin.ModelAdmin):
    list_display = ("lesson", "phrase_jp", "level_code")
    list_filter = ("level_code",)
    search_fields = ("phrase_jp",)


@admin.register(UserPracticeMark)
class UserPracticeMarkAdmin(admin.ModelAdmin):
    """Chỉ đọc — dữ liệu của người học."""

    list_display = ("user", "kind", "object_id", "is_known", "times", "last_at")
    list_filter = ("kind", "is_known")
    search_fields = ("user__username",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
