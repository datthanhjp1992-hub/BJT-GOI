from django.contrib import admin

from .models import Topic, Vocabulary, ExampleSentence


class ExampleSentenceInline(admin.TabularInline):
    model = ExampleSentence
    extra = 1


@admin.register(Vocabulary)
class VocabularyAdmin(admin.ModelAdmin):
    list_display = ("word", "reading", "meaning_vi", "bjt_level", "updated_at")
    list_filter = ("bjt_level", "topics")
    search_fields = ("word", "reading", "meaning_vi")
    inlines = [ExampleSentenceInline]


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
