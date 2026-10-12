"""Đăng ký model vocabulary vào Django admin.

**Vì sao chủ đề phải là inline, không phải một ô chọn nhiều:**
`Vocabulary.topics` là ManyToMany đi qua `through="vocabulary.VocabularyTopic"`.
Django CỐ Ý loại mọi M2M có bảng nối tự khai ra khỏi ModelForm (và do đó khỏi
form của admin), vì nó không biết điền các cột phụ của bảng nối — ở đây là 4 cột
audit created_by/created_at/updated_by/updated_at. Nếu chỉ khai `filter_horizontal
= ("topics",)` thì admin sẽ báo lỗi hệ thống, còn không khai gì thì màn "Thêm
vocabulary" mất hẳn phần chủ đề (đúng hiện tượng đã gặp).

Inline dưới đây tạo thẳng row `VocabularyTopic` qua `save()`, nên gán chủ đề ở
admin vẫn ghi đủ audit — khác với `vocab.topics.add()` (đi qua bulk_create, bỏ
qua save(), để trống created_by).
"""
from django.contrib import admin

from .models import ExampleSentence, Topic, Vocabulary, VocabularyTopic


class SoftDeleteAdmin(admin.ModelAdmin):
    """Bảng xoá mềm (Vocabulary, Topic): liệt kê CẢ dòng đã xoá — lọc bằng cột
    "is deleted". Nút xoá thật bị tắt; dùng 2 action Xoá mềm / Khôi phục."""

    actions = ["soft_delete_selected", "restore_selected"]

    def get_queryset(self, request):
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        return qs.order_by(*ordering) if ordering else qs

    def get_search_results(self, request, queryset, search_term):
        # Ô autocomplete ở màn khác không được gợi ý dòng đã xoá.
        if request.path.endswith("/autocomplete/"):
            queryset = queryset.filter(is_deleted=False)
        return super().get_search_results(request, queryset, search_term)

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Xoá mềm các dòng đã chọn")
    def soft_delete_selected(self, request, queryset):
        for obj in queryset.filter(is_deleted=False):
            obj.soft_delete()

    @admin.action(description="Khôi phục các dòng đã chọn")
    def restore_selected(self, request, queryset):
        for obj in queryset.filter(is_deleted=True):
            obj.restore()


class ExampleSentenceInline(admin.TabularInline):
    model = ExampleSentence
    extra = 1


class VocabularyTopicInline(admin.TabularInline):
    """Gán từ vào chủ đề — thay cho ô chọn nhiều mà Django không dựng được."""

    model = VocabularyTopic
    extra = 1
    autocomplete_fields = ("topic",)
    verbose_name = "Chủ đề"
    verbose_name_plural = "Chủ đề"


@admin.register(Vocabulary)
class VocabularyAdmin(SoftDeleteAdmin):
    list_display = ("word", "reading", "han_viet", "meaning_vi", "topic_list", "is_deleted", "updated_at")
    list_filter = ("is_deleted", "topics")
    search_fields = ("word", "reading", "han_viet", "meaning_vi")
    inlines = [VocabularyTopicInline, ExampleSentenceInline]

    def get_queryset(self, request):
        # Không có prefetch thì cột "Chủ đề" bắn thêm 1 query mỗi dòng.
        return super().get_queryset(request).prefetch_related("topics")

    @admin.display(description="Chủ đề")
    def topic_list(self, obj):
        return ", ".join(t.display_name for t in obj.topics.all()) or "—"


class VocabularyInline(admin.TabularInline):
    """Xem nhanh các từ đang thuộc chủ đề, ngay trong màn sửa chủ đề."""

    model = VocabularyTopic
    extra = 0
    autocomplete_fields = ("vocabulary",)
    verbose_name = "Từ vựng"
    verbose_name_plural = "Từ vựng trong chủ đề"


@admin.register(Topic)
class TopicAdmin(SoftDeleteAdmin):
    list_display = ("name", "name_ja", "slug", "word_count", "is_deleted")
    list_filter = ("is_deleted",)
    search_fields = ("name", "name_ja", "slug")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [VocabularyInline]

    @admin.display(description="Số từ")
    def word_count(self, obj):
        return obj.vocabularies.count()
