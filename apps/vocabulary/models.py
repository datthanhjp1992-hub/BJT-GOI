"""
Core vocabulary content models.
All inherit AuditableModel -> created_by/created_at/updated_by/updated_at.
"""
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.contrib.postgres.search import TrigramSimilarity
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Greatest

from apps.core.models import AuditableModel
from apps.core.constants import bjt_level_choices


class Topic(AuditableModel):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    icon_emoji = models.CharField(max_length=8, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class VocabularyQuerySet(models.QuerySet):
    def search(self, query, limit=50, min_similarity=0.15):
        """Tìm gần đúng theo 表記 hoặc よみ.

        Dùng trigram similarity nên chấp nhận người học gõ thiếu/sai kana —
        "ちゅもんする" vẫn ra 注文する. Nhánh icontains giữ lại để chuỗi quá ngắn
        (1-2 ký tự, similarity luôn thấp) vẫn tìm được; cả hai nhánh đều ăn
        index GIN trigram khai ở Meta.indexes.
        """
        q = (query or "").strip()
        if not q:
            return self.none()
        return (
            self.annotate(
                score=Greatest(
                    TrigramSimilarity("word", q),
                    TrigramSimilarity("reading", q),
                )
            )
            .filter(Q(score__gte=min_similarity) | Q(word__icontains=q) | Q(reading__icontains=q))
            .order_by("-score", "bjt_level")[:limit]
        )


class Vocabulary(AuditableModel):
    word = models.CharField(max_length=100, help_text="Kanji/kana form, e.g. 注文する")
    reading = models.CharField(max_length=150, help_text="Furigana reading, e.g. ちゅうもんする")
    meaning_vi = models.CharField(max_length=255)
    bjt_level = models.CharField(max_length=3, choices=bjt_level_choices, default="J5")
    audio_url = models.URLField(blank=True)  # reserved for future use
    topics = models.ManyToManyField(
        Topic, related_name="vocabularies", blank=True,
        through="vocabulary.VocabularyTopic",
    )

    objects = VocabularyQuerySet.as_manager()

    class Meta:
        verbose_name_plural = "vocabularies"
        indexes = [
            models.Index(fields=["bjt_level"]),
            # GIN trigram: tìm gần đúng và ILIKE '%...%' trên 表記 / よみ mà
            # không phải quét toàn bảng. Cần extension pg_trgm — bật ở
            # migration 0002_trigram_search.
            GinIndex(
                OpClass(F("word"), name="gin_trgm_ops"),
                name="vocab_word_trgm",
            ),
            GinIndex(
                OpClass(F("reading"), name="gin_trgm_ops"),
                name="vocab_reading_trgm",
            ),
        ]
        constraints = [
            # Khoá tự nhiên là CẶP (word, reading), không phải riêng word:
            # 同形異音語 cùng mặt chữ khác cách đọc là hai từ khác hẳn nhau —
            # 目下「めした」cấp dưới vs 目下「もっか」hiện nay,
            # 大家「おおや」chủ nhà vs 大家「たいか」bậc thầy.
            # Ràng buộc này cho phép script import dùng update_or_create() và
            # chạy lại bao nhiêu lần cũng ra cùng kết quả.
            models.UniqueConstraint(
                fields=["word", "reading"], name="uniq_vocab_word_reading"
            ),
        ]

    def __str__(self):
        return f"{self.word} ({self.reading})"


class ExampleSentence(AuditableModel):
    vocabulary = models.ForeignKey(Vocabulary, related_name="examples", on_delete=models.CASCADE)
    sentence_jp = models.CharField(max_length=255)
    sentence_vi = models.CharField(max_length=255)

    def __str__(self):
        return self.sentence_jp


class VocabularyTopic(AuditableModel):
    """Bảng nối Vocabulary <-> Topic.

    Khai tường minh (thay vì để Django tự sinh bảng ẩn) để bảng nối cũng có đủ
    4 cột audit created_at/created_by/updated_at/updated_by như mọi bảng khác.

    LƯU Ý: `vocab.topics.add(topic)` đi qua bulk_create nên KHÔNG gọi save() —
    created_by/updated_by sẽ để trống. Muốn có actor thì tạo thẳng:
    `VocabularyTopic.objects.create(vocabulary=v, topic=t)`.
    """

    vocabulary = models.ForeignKey(Vocabulary, related_name="topic_links", on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, related_name="vocabulary_links", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("vocabulary", "topic")
        verbose_name = "Vocabulary-Topic link"

    def __str__(self):
        return f"{self.vocabulary_id} - {self.topic_id}"
