from django.contrib import admin

from .models import ExamAnswer, ExamAttempt, ExamOption, ExamQuestion, ExamSet, WrongBookEntry


@admin.register(ExamSet)
class ExamSetAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "slug", "is_active")
    list_editable = ("is_active",)


class ExamOptionInline(admin.TabularInline):
    model = ExamOption
    extra = 0
    fields = ("position", "text_jp", "is_correct")


@admin.register(ExamQuestion)
class ExamQuestionAdmin(admin.ModelAdmin):
    list_display = ("exam_set", "number", "part", "section_code", "short_stem", "is_active")
    list_filter = ("exam_set", "section_code", "is_active")
    search_fields = ("stem_jp", "passage_jp", "source_ref")
    list_editable = ("is_active",)
    inlines = [ExamOptionInline]

    @admin.display(description="Câu hỏi")
    def short_stem(self, obj):
        return obj.stem_jp[:60]


class ExamAnswerInline(admin.TabularInline):
    model = ExamAnswer
    extra = 0
    can_delete = False
    fields = ("order", "question_type_code", "vocabulary", "question", "selected", "is_correct", "time_ms")
    readonly_fields = fields


@admin.register(ExamAttempt)
class ExamAttemptAdmin(admin.ModelAdmin):
    """Chỉ đọc — lượt làm bài là dữ liệu của người học."""

    list_display = ("user", "kind_code", "mode_code", "score", "total", "started_at", "finished_at")
    list_filter = ("kind_code", "mode_code")
    search_fields = ("user__username",)
    inlines = [ExamAnswerInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WrongBookEntry)
class WrongBookEntryAdmin(admin.ModelAdmin):
    list_display = ("user", "question", "vocabulary", "question_type_code", "wrong_count",
                    "correct_streak", "cleared_at")
    list_filter = ("question_type_code",)
    search_fields = ("user__username", "vocabulary__word")
    raw_id_fields = ("question", "vocabulary")
