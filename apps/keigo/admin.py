"""Đăng ký model kính ngữ vào Django admin.

Quy ước lấy từ apps/vocabulary/admin.py: bảng con luôn là inline của bảng cha
để sửa tại chỗ, và mọi FK chọn-một-trong-nhiều dùng autocomplete_fields (bảng
đích phải có search_fields, nếu không Django báo admin.E040).
"""
from django.contrib import admin

from .models import (
    ExerciseSection,
    ExerciseSet,
    KeigoExample,
    KeigoForm,
    KeigoLesson,
    KeigoPattern,
    KeigoPhrasePair,
    KeigoVerb,
    Question,
    QuestionOption,
    UserExerciseAttempt,
    UserQuestionAnswer,
)


# --------------------------------------------------------------------------
# Nội dung kính ngữ
# --------------------------------------------------------------------------


class KeigoFormInline(admin.TabularInline):
    model = KeigoForm
    extra = 1
    fields = ("style_code", "form", "reading", "is_irregular", "note_vi", "display_order")
    verbose_name = "Dạng kính ngữ"
    verbose_name_plural = "Dạng kính ngữ"


@admin.register(KeigoVerb)
class KeigoVerbAdmin(admin.ModelAdmin):
    list_display = ("plain_form", "reading", "meaning_vi", "form_count", "display_order")
    search_fields = ("plain_form", "reading", "meaning_vi")
    inlines = [KeigoFormInline]
    ordering = ("display_order", "plain_form")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("forms")

    @admin.display(description="Số dạng")
    def form_count(self, obj):
        return obj.forms.count()


@admin.register(KeigoForm)
class KeigoFormAdmin(admin.ModelAdmin):
    """Đăng ký riêng (ngoài inline) để lọc nhanh theo loại kính ngữ khi soát dữ liệu."""

    list_display = ("verb", "style_code", "form", "reading", "is_irregular")
    list_filter = ("style_code", "is_irregular")
    search_fields = ("form", "reading", "verb__plain_form")
    autocomplete_fields = ("verb", "vocabulary")


class KeigoExampleInline(admin.TabularInline):
    model = KeigoExample
    extra = 1
    fields = ("sentence_jp", "sentence_vi", "speaker", "is_correct", "pair_group", "display_order")


@admin.register(KeigoPattern)
class KeigoPatternAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "lesson", "style_code", "display_order")
    list_filter = ("lesson", "style_code")
    search_fields = ("code", "title", "formation")
    autocomplete_fields = ("lesson",)
    inlines = [KeigoExampleInline]


@admin.register(KeigoPhrasePair)
class KeigoPhrasePairAdmin(admin.ModelAdmin):
    list_display = ("pair_type", "casual", "polite", "group_label", "display_order")
    list_filter = ("pair_type", "lesson")
    search_fields = ("casual", "polite", "group_label")
    autocomplete_fields = ("lesson",)


@admin.register(KeigoLesson)
class KeigoLessonAdmin(admin.ModelAdmin):
    list_display = ("display_order", "title", "slug", "style_code", "pattern_count", "pair_count")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    ordering = ("display_order",)

    @admin.display(description="Số mẫu")
    def pattern_count(self, obj):
        return obj.patterns.count()

    @admin.display(description="Số cặp từ")
    def pair_count(self, obj):
        return obj.phrase_pairs.count()


# --------------------------------------------------------------------------
# Bài tập
# --------------------------------------------------------------------------


class ExerciseSectionInline(admin.TabularInline):
    model = ExerciseSection
    extra = 0
    fields = ("number", "instruction_jp", "passage_jp", "display_order")


@admin.register(ExerciseSet)
class ExerciseSetAdmin(admin.ModelAdmin):
    list_display = ("display_order", "title", "slug", "question_count", "actual_count", "khop")
    search_fields = ("title", "slug")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ExerciseSectionInline]
    ordering = ("display_order",)

    def _actual(self, obj):
        return Question.objects.filter(section__exercise_set=obj).count()

    @admin.display(description="Số câu thật")
    def actual_count(self, obj):
        return self._actual(obj)

    @admin.display(description="Khớp?", boolean=True)
    def khop(self, obj):
        """Cột này là lý do màn danh sách bộ đề đáng để mở: lệch giữa
        question_count (đếm từ bảng đáp án) và số câu thật là dấu hiệu nhập
        thiếu, mà nhìn từng bộ thì không thấy."""
        return self._actual(obj) == obj.question_count


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 0
    fields = ("position", "text_jp", "is_correct")


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("code", "section", "number", "question_type", "star_position", "correct_order")
    list_filter = ("question_type", "section__exercise_set")
    search_fields = ("code", "stem_jp")
    autocomplete_fields = ("section",)
    inlines = [QuestionOptionInline]


@admin.register(ExerciseSection)
class ExerciseSectionAdmin(admin.ModelAdmin):
    """Cần đăng ký để QuestionAdmin dùng được autocomplete_fields = ("section",)."""

    list_display = ("exercise_set", "number", "has_passage", "question_count")
    list_filter = ("exercise_set",)
    search_fields = ("exercise_set__slug", "exercise_set__title", "instruction_jp")
    autocomplete_fields = ("exercise_set",)

    @admin.display(description="Có đoạn văn", boolean=True)
    def has_passage(self, obj):
        return bool(obj.passage_jp)

    @admin.display(description="Số câu")
    def question_count(self, obj):
        return obj.questions.count()


class UserQuestionAnswerInline(admin.TabularInline):
    model = UserQuestionAnswer
    extra = 0
    fields = ("question", "selected_option", "selected_order", "is_correct")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(UserExerciseAttempt)
class UserExerciseAttemptAdmin(admin.ModelAdmin):
    """Bản ghi lịch sử — chỉ xem, không sửa tay."""

    list_display = ("user", "exercise_set", "score", "total", "started_at", "finished_at")
    list_filter = ("exercise_set",)
    search_fields = ("user__username",)
    readonly_fields = ("user", "exercise_set", "score", "total", "started_at", "finished_at")
    inlines = [UserQuestionAnswerInline]

    def has_add_permission(self, request):
        return False
