"""
Logic nghiệp vụ của app learning:

1. Lịch ôn tập SM-2 (`review_word`) — quality 0-5 quy từ 4 nút Quên/Khó/Nhớ/Dễ.
2. Số liệu cho SC03_TrangChu (`get_learning_stats`, `get_streak_days`,
   `get_topic_in_progress`, `get_suggested_topics`).

View chỉ gọi xuống đây rồi đẩy vào template — không tự viết truy vấn.
"""
from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate

import random

from apps.vocabulary.models import Topic, Vocabulary

from .models import StudySession, UserVocabularyProgress

QUALITY_MAP = {
    "quen": 0,   # "Forgot" button
    "kho": 3,    # "Hard" button
    "nho": 4,    # "Remembered" button
    "de": 5,     # "Easy" button
}


def get_flashcard_queue(user, topic):
    """Hàng đợi ôn tập flashcard của 1 chủ đề (SC04).

    Ưu tiên từ ĐẾN HẠN (next_review_date <= hôm nay theo giờ user, quá hạn lâu
    nhất xếp trước), hết thì tới từ CHƯA HỌC LẦN NÀO (chưa có
    UserVocabularyProgress) theo thứ tự bảng chữ cái.

    Không cần tự loại thẻ vừa ôn khỏi hàng đợi: review_word() luôn đẩy
    next_review_date sang ít nhất NGÀY MAI (interval_days >= 1 dù quality nào),
    nên thẻ vừa ôn tự rời khỏi cả hai nhánh truy vấn ở lần gọi kế tiếp.
    """
    today = user.local_today()
    due = (
        Vocabulary.objects.filter(
            topics=topic, progress__user=user, progress__next_review_date__lte=today,
        )
        .order_by("progress__next_review_date", "word")
    )
    new_words = (
        Vocabulary.objects.filter(topics=topic)
        .exclude(progress__user=user)
        .order_by("word")
    )
    return list(due) + list(new_words)


QUIZ_CHOICE_COUNT = 4


def get_quiz_choices(word, topic, count=QUIZ_CHOICE_COUNT):
    """`count` lựa chọn cho câu hỏi trắc nghiệm SC06: 1 đúng (`word`) + tối đa
    (count - 1) đáp án nhiễu, đã xáo trộn vị trí.

    Ưu tiên lấy nhiễu CÙNG CHỦ ĐỀ (nghĩa dễ gây nhầm lẫn hơn nghĩa ở chủ đề
    khác); chủ đề ít từ thì bù thêm từ TOÀN BỘ từ điển để vẫn đủ số lựa chọn
    khi kho từ đủ lớn. Từ điển/chủ đề quá nhỏ (vd môi trường test) thì trả về
    ÍT HƠN count lựa chọn — tốt hơn là ném lỗi giữa lúc người học đang làm bài.
    """
    same_topic = list(Vocabulary.objects.filter(topics=topic).exclude(pk=word.pk))
    needed = (count - 1) - len(same_topic)
    if needed > 0:
        exclude_ids = {v.pk for v in same_topic} | {word.pk}
        same_topic += list(
            Vocabulary.objects.exclude(pk__in=exclude_ids).order_by("?")[:needed]
        )

    distractors = random.sample(same_topic, k=min(count - 1, len(same_topic)))
    choices = [word] + distractors
    random.shuffle(choices)
    return choices


def review_word(progress, quality: int):
    """Update a UserVocabularyProgress instance in place using SM-2."""
    if quality < 3:
        progress.srs_level = 0
        progress.interval_days = 1
        progress.wrong_count += 1
    else:
        progress.correct_count += 1
        if progress.srs_level == 0:
            progress.interval_days = 1
        elif progress.srs_level == 1:
            progress.interval_days = 6
        else:
            progress.interval_days = round(progress.interval_days * progress.ease_factor)
        progress.srs_level += 1

    progress.ease_factor = max(
        1.3,
        progress.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
    )
    # "Hôm nay" tính theo múi giờ của NGƯỜI HỌC (User.timezone), không phải
    # TIME_ZONE của server — nếu không, người dùng ở Việt Nam sẽ thấy thẻ đến
    # hạn lệch 2 tiếng so với mốc nửa đêm của họ.
    today = progress.user.local_today()
    progress.next_review_date = today + timedelta(days=progress.interval_days)
    progress.is_mastered = progress.srs_level >= 5
    progress.save()
    return progress


# =============================================================================
# Số liệu cho SC03_TrangChu (dashboard)
# -----------------------------------------------------------------------------
# Mọi mốc thời gian ở đây tính theo MÚI GIỜ CỦA NGƯỜI HỌC (User.timezone),
# không theo TIME_ZONE của server — cùng lý do đã ghi ở review_word().
# =============================================================================

STREAK_LOOKBACK_DAYS = 400  # chặn trên cho query streak, đủ cho chuỗi hơn 1 năm


def get_streak_days(user):
    """Số ngày học liên tục tính tới hôm nay (theo giờ của user).

    Học hôm nay -> chuỗi tính từ hôm nay. Chưa học hôm nay nhưng hôm qua có
    -> chuỗi vẫn giữ (người dùng chưa "mất" streak khi ngày còn chưa hết).
    Cả hai ngày đều trống -> 0.

    TruncDate nhận tzinfo nên PostgreSQL tự đổi múi giờ trong SQL; hàm chỉ
    kéo về danh sách NGÀY duy nhất, không kéo về từng phiên học.
    """
    tz = user.tzinfo
    today = user.local_today()
    # started_at là DateTimeField aware; so sánh với một `date` trần sẽ bị
    # Django cảnh báo "naive datetime" và diễn giải theo TIME_ZONE của server.
    # Dựng mốc aware theo đúng nửa đêm của NGƯỜI HỌC.
    since = datetime.combine(
        today - timedelta(days=STREAK_LOOKBACK_DAYS), time.min, tzinfo=tz
    )

    study_days = set(
        StudySession.objects.filter(user=user, started_at__gte=since)
        .annotate(day=TruncDate("started_at", tzinfo=tz))
        .values_list("day", flat=True)
        .distinct()
    )
    if not study_days:
        return 0

    cursor = today
    if cursor not in study_days:
        cursor -= timedelta(days=1)
        if cursor not in study_days:
            return 0

    streak = 0
    while cursor in study_days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_learning_stats(user):
    """3 ô số liệu đầu trang chủ, gộp về 1 query trên bảng tiến độ."""
    today = user.local_today()
    stats = UserVocabularyProgress.objects.filter(user=user).aggregate(
        words_started=Count("pk"),
        words_mastered=Count("pk", filter=Q(is_mastered=True)),
        due_today=Count("pk", filter=Q(next_review_date__lte=today)),
    )
    stats["streak_days"] = get_streak_days(user)
    return stats


def get_topic_in_progress(user):
    """Chủ đề để nút "Học tiếp" trỏ tới, kèm tiến độ.

    Ưu tiên chủ đề của PHIÊN HỌC gần nhất (đúng nghĩa "đang học dở"); chưa
    có phiên nào thì lấy chủ đề mà user có nhiều từ đang theo dõi nhất.
    Trả None nếu user chưa động vào chủ đề nào — template sẽ hiện gợi ý.
    """
    last_session = (
        StudySession.objects.filter(user=user, topic__isnull=False)
        .select_related("topic")
        .order_by("-started_at")
        .first()
    )
    topic = last_session.topic if last_session else None

    if topic is None:
        row = (
            UserVocabularyProgress.objects.filter(user=user, vocabulary__topics__isnull=False)
            .values("vocabulary__topics")
            .annotate(n=Count("pk"))
            .order_by("-n")
            .first()
        )
        if row:
            topic = Topic.objects.filter(pk=row["vocabulary__topics"]).first()

    if topic is None:
        return None

    total = topic.vocabularies.count()
    learned = UserVocabularyProgress.objects.filter(
        user=user, vocabulary__topics=topic
    ).count()
    return {
        "topic": topic,
        "learned": learned,
        "total": total,
        "percent": round(learned * 100 / total) if total else 0,
    }


def get_suggested_topics(user, limit=3):
    """Chủ đề gợi ý: ưu tiên chủ đề user CHƯA đụng tới, nhiều từ nhất trước.

    Nếu user đã đụng hết mọi chủ đề thì lấp cho đủ `limit` bằng các chủ đề
    còn lại — trang chủ không bao giờ để trống mục này khi DB có dữ liệu.
    """
    studied_topic_ids = set(
        UserVocabularyProgress.objects.filter(user=user)
        .values_list("vocabulary__topics", flat=True)
        .distinct()
    )
    studied_topic_ids.discard(None)

    base = (
        Topic.objects.annotate(word_count=Count("vocabularies", distinct=True))
        .filter(word_count__gt=0)
        .order_by("-word_count", "name")
    )
    topics = list(base.exclude(pk__in=studied_topic_ids)[:limit])
    if len(topics) < limit:
        topics += list(base.exclude(pk__in=[t.pk for t in topics])[: limit - len(topics)])

    return topics


def get_recent_topics(user, limit=5):
    """Chủ đề gần đây user có học/ôn (SC09 Hồ sơ cá nhân) — sắp xếp theo
    StudySession MỚI NHẤT của mỗi chủ đề, kèm tiến độ (đã học/tổng số từ).

    Khác `get_topic_in_progress()` (SC03) ở chỗ trả về NHIỀU chủ đề chứ không
    chỉ 1 — dashboard chỉ cần điểm "học tiếp ở đâu", còn hồ sơ cần liệt kê cả
    lịch sử gần đây.
    """
    topic_ids_in_order = (
        StudySession.objects.filter(user=user, topic__isnull=False)
        .order_by("-started_at")
        .values_list("topic_id", flat=True)
    )
    # Khử trùng nhưng GIỮ THỨ TỰ xuất hiện đầu tiên (= gần đây nhất) — không
    # dùng .distinct() vì nó không đảm bảo thứ tự trên cột đã annotate/order.
    seen_ids = []
    for topic_id in topic_ids_in_order:
        if topic_id not in seen_ids:
            seen_ids.append(topic_id)
        if len(seen_ids) >= limit:
            break

    topics_by_id = Topic.objects.in_bulk(seen_ids)

    result = []
    for topic_id in seen_ids:
        topic = topics_by_id.get(topic_id)
        if topic is None:
            continue  # chủ đề đã bị xoá sau khi StudySession được ghi
        total = topic.vocabularies.count()
        learned = UserVocabularyProgress.objects.filter(
            user=user, vocabulary__topics=topic
        ).count()
        result.append({
            "topic": topic,
            "learned": learned,
            "total": total,
            "percent": round(learned * 100 / total) if total else 0,
        })
    return result


def get_greeting_label_key(user):
    """Key label cho lời chào theo giờ ĐỊA PHƯƠNG của user."""
    hour = user.local_now().hour
    if hour < 12:
        return "learning.dashboard.eyebrow.morning"
    if hour < 18:
        return "learning.dashboard.eyebrow.afternoon"
    return "learning.dashboard.eyebrow.evening"
