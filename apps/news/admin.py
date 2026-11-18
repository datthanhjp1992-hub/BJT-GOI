from django.contrib import admin

from .models import NewsLesson, NewsSegment


class NewsSegmentInline(admin.StackedInline):
    model = NewsSegment
    extra = 0


@admin.register(NewsLesson)
class NewsLessonAdmin(admin.ModelAdmin):
    list_display = ("number", "title_jp", "title_vi")
    inlines = [NewsSegmentInline]
