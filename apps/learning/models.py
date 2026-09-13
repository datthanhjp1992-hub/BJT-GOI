"""
Learning-progress models: spaced-repetition state per (user, vocabulary),
plus a log of study sessions used for the dashboard's streak/stat cards.
"""
from django.conf import settings
from django.db import models

from apps.core.constants import session_type_choices
from apps.core.models import AuditableModel
from apps.vocabulary.models import Vocabulary


class UserVocabularyProgress(AuditableModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="progress", on_delete=models.CASCADE)
    vocabulary = models.ForeignKey(Vocabulary, related_name="progress", on_delete=models.CASCADE)

    # SM-2 spaced repetition state
    srs_level = models.PositiveSmallIntegerField(default=0)
    ease_factor = models.FloatField(default=2.5)
    interval_days = models.PositiveIntegerField(default=0)
    # DateField chứ không phải DateTimeField là CỐ Ý: SRS làm việc theo ngày,
    # thẻ phải đến hạn từ đầu ngày của người học chứ không phải đúng giờ phút
    # của lần ôn trước. Mốc "hôm nay" lấy theo User.local_today() (múi giờ của
    # user), không theo TIME_ZONE của server — xem apps/learning/services.py.
    next_review_date = models.DateField(null=True, blank=True)

    correct_count = models.PositiveIntegerField(default=0)
    wrong_count = models.PositiveIntegerField(default=0)
    is_mastered = models.BooleanField(default=False)

    class Meta:
        unique_together = ("user", "vocabulary")
        indexes = [models.Index(fields=["user", "next_review_date"])]


class StudySession(AuditableModel):
    """One flashcard/quiz session log, used to compute streaks & history."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="study_sessions", on_delete=models.CASCADE)
    topic = models.ForeignKey("vocabulary.Topic", null=True, blank=True, on_delete=models.SET_NULL)
    session_type = models.CharField(max_length=20, choices=session_type_choices)
    words_reviewed = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Streak và biểu đồ lịch sử luôn lọc theo (user, thời gian giảm dần).
        indexes = [models.Index(fields=["user", "-started_at"])]


class UserWordlist(AuditableModel):
    """A user-curated custom list of words (e.g. selected for a practice sheet)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="wordlists", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    words = models.ManyToManyField(
        Vocabulary, related_name="in_wordlists", blank=True,
        through="learning.UserWordlistWord",
    )

    def __str__(self):
        return self.name


class UserWordlistWord(AuditableModel):
    """Bảng nối UserWordlist <-> Vocabulary, khai tường minh để có đủ 4 cột audit.

    Xem ghi chú ở apps.vocabulary.models.VocabularyTopic về .add() và created_by.
    """

    wordlist = models.ForeignKey(UserWordlist, related_name="word_links", on_delete=models.CASCADE)
    vocabulary = models.ForeignKey(Vocabulary, related_name="wordlist_links", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("wordlist", "vocabulary")
        verbose_name = "Wordlist-Vocabulary link"

    def __str__(self):
        return f"{self.wordlist_id} - {self.vocabulary_id}"
