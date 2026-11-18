"""Luyện nghe dịch qua bản tin — docs/SPEC_NGHE_BAN_TIN.md.

Tiến độ "đã luyện" không có bảng riêng: dùng lessons.UserPracticeMark với kind="news",
object_id = NewsLesson.id (mức bài).
"""
from django.db import models

from apps.core.models import AuditableModel


class NewsLesson(AuditableModel):
    number = models.PositiveSmallIntegerField(unique=True)
    title_jp = models.CharField(max_length=200)
    title_vi = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["number"]
        verbose_name = "Bài nghe bản tin"
        verbose_name_plural = "Bài nghe bản tin"

    def __str__(self):
        return f"第{self.number}課 {self.title_jp}"


class NewsSegment(AuditableModel):
    lesson = models.ForeignKey(NewsLesson, related_name="segments", on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()
    text_jp = models.TextField()
    translation_vi = models.TextField(blank=True)
    audio_url = models.URLField(blank=True)  # VOICEVOX trên Supabase — scripts/generate_news_audio.py

    class Meta:
        ordering = ["lesson", "number"]
        constraints = [models.UniqueConstraint(fields=["lesson", "number"], name="uniq_news_segment")]
        verbose_name = "Đoạn bản tin"
        verbose_name_plural = "Đoạn bản tin"

    def __str__(self):
        return f"{self.lesson.number}-{self.number}"
