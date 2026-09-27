"""
Logic nghiệp vụ của app learning:

1. Lịch ôn tập (`review_word`) — SM-2 có bước học theo phút, xem `srs.py`;
   quality 0-5 quy từ 4 nút Quên/Khó/Nhớ/Dễ. Hàng đợi SC04 (`get_topic_queue`).
2. Số liệu cho SC03_TrangChu (`get_learning_stats`, `get_streak_days`,
   `get_topic_in_progress`, `get_suggested_topics`).

View chỉ gọi xuống đây rồi đẩy vào template — không tự viết truy vấn.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

import random

from apps.vocabulary.models import Topic, Vocabulary

from . import srs
from .models import StudySession, UserVocabularyProgress

QUALITY_MAP = {
    "quen": 0,   # "Forgot" button
    "kho": 3,    # "Hard" button
    "nho": 4,    # "Remembered" button
    "de": 5,     # "Easy" button
}


def local_day_start(user, day=None):
    """Nửa đêm (aware) của ngày `day` theo múi giờ NGƯỜI HỌC."""
    return datetime.combine(day or user.local_today(), time.min, tzinfo=user.tzinfo)


def count_new_words_today(user):
    """Số từ học LẦN ĐẦU hôm nay (theo giờ người học) = số dòng tiến độ tạo hôm nay.

    Không cần bảng log riêng: dòng UserVocabularyProgress chỉ sinh ra khi từ
    được chấm lần đầu (`get_or_start_progress`), và hoàn tác lần chấm đó thì
    xoá luôn dòng — nên con số này tự khớp.
    """
    return UserVocabularyProgress.objects.filter(
        user=user, created_at__gte=local_day_start(user)
    ).count()


def count_due_tomorrow(user):
    tomorrow = user.local_today() + timedelta(days=1)
    return UserVocabularyProgress.objects.filter(
        user=user, card_state=srs.REVIEW, next_review_date=tomorrow
    ).count()


@dataclass
class TopicQueue:
    """Hàng đợi một phiên SC04 kèm các con số hiển thị trên màn học."""

    words: list = field(default_factory=list)
    n_new: int = 0
    n_learning: int = 0
    n_review: int = 0
    new_limit: int = 0
    new_today: int = 0
    more_new: bool = False            # còn từ mới nhưng đã chạm hạn mức/ngày
    more_new_count: int = 0           # số từ mới còn bị giữ lại vì hạn mức
    ahead_minutes: int = 0            # >0: từ đầu hàng là từ đang học CHƯA tới giờ

    @property
    def remaining(self):
        return self.n_new + self.n_learning + self.n_review


def get_topic_queue(user, topic, now=None, unlocked_ids=()):
    """Hàng đợi SC04/SC06 của một chủ đề, theo đúng flow ôn tập:

    1. Từ ĐANG HỌC / HỌC LẠI đã tới giờ (bước học tính bằng phút).
    2. Từ ĐẾN HẠN ôn (next_review_date <= hôm nay), quá hạn lâu nhất trước.
    3. Từ MỚI theo bảng chữ cái, tối đa `user.daily_review_goal` từ/ngày
       (tính chung mọi chủ đề — xem count_new_words_today).
    4. Hết cả ba thì học trước từ đang học chưa tới giờ (sớm nhất trước) —
       người học không phải ngồi chờ 10 phút; ahead_minutes cho biết còn bao lâu.

    "Hôm nay" tính theo múi giờ của user (User.local_today()).

    `unlocked_ids`: từ mới người học chủ động mở thêm hôm nay bằng nút "Học
    thêm N từ mới" (vượt hạn mức, chỉ cho chủ đề này) — xem
    `pick_extra_new_words()`. Chúng được xếp vào nhóm từ mới dù hạn mức đã hết.
    """
    now = now or timezone.now()
    today = user.local_today()
    progress = {
        p.vocabulary_id: p
        for p in UserVocabularyProgress.objects.filter(user=user, vocabulary__topics=topic)
    }
    learning = sorted(
        (p for p in progress.values() if p.card_state in srs.IN_SESSION_STATES),
        key=lambda p: (p.due_at or now, p.vocabulary_id),
    )
    learn_due = [p for p in learning if (p.due_at or now) <= now]
    learn_ahead = [p for p in learning if (p.due_at or now) > now]
    review_due = sorted(
        (
            p for p in progress.values()
            if p.card_state == srs.REVIEW
            and (p.next_review_date is None or p.next_review_date <= today)
        ),
        key=lambda p: (p.next_review_date or date.min, p.vocabulary_id),
    )

    new_limit = user.daily_review_goal
    new_today = count_new_words_today(user)
    new_left = max(0, new_limit - new_today)
    unseen = Vocabulary.objects.filter(topics=topic).exclude(progress__user=user).order_by("word")
    new_words = list(unseen[:new_left]) if new_left else []
    if unlocked_ids:
        taken = {w.pk for w in new_words}
        new_words += [
            w for w in unseen.filter(pk__in=unlocked_ids) if w.pk not in taken
        ]
        new_words.sort(key=lambda w: w.word)
    more_new_count = unseen.count() - len(new_words)

    by_id = Vocabulary.objects.in_bulk(
        [p.vocabulary_id for p in learning] + [p.vocabulary_id for p in review_due]
    )
    ordered = (
        [by_id[p.vocabulary_id] for p in learn_due if p.vocabulary_id in by_id]
        + [by_id[p.vocabulary_id] for p in review_due if p.vocabulary_id in by_id]
        + new_words
        + [by_id[p.vocabulary_id] for p in learn_ahead if p.vocabulary_id in by_id]
    )
    ahead = 0
    if ordered and not learn_due and not review_due and not new_words:
        ahead = max(1, round((learn_ahead[0].due_at - now).total_seconds() / 60))
    return TopicQueue(
        words=ordered,
        n_new=len(new_words),
        n_learning=len(learning),
        n_review=len(review_due),
        new_limit=new_limit,
        new_today=new_today,
        # Chỉ báo "hết hạn mức" khi hạn mức hôm nay thật sự đã dùng hết.
        more_new=new_left == 0 and more_new_count > 0,
        more_new_count=more_new_count,
        ahead_minutes=ahead,
    )


def pick_extra_new_words(user, topic, count=None):
    """Id các từ mới (chưa học lần nào) của `topic` để mở thêm hôm nay khi đã
    chạm hạn mức — tối đa `count` từ (mặc định = hạn mức mỗi ngày), cùng thứ
    tự bảng chữ cái với hàng đợi."""
    count = count or user.daily_review_goal or 1
    unseen = Vocabulary.objects.filter(topics=topic).exclude(progress__user=user).order_by("word")
    return list(unseen.values_list("pk", flat=True)[:count])


def get_flashcard_queue(user, topic):
    """Danh sách từ theo thứ tự học của SC04 — xem get_topic_queue()."""
    return get_topic_queue(user, topic).words


QUIZ_CHOICE_COUNT = 4


def get_quiz_choices(word, topic, count=QUIZ_CHOICE_COUNT):
    """`count` lựa chọn cho câu hỏi trắc nghiệm SC06: 1 đúng (`word`) + tối đa
    (count - 1) đáp án nhiễu, đã xáo trộn vị trí.

    Ưu tiên lấy nhiễu CÙNG CHỦ ĐỀ (nghĩa dễ gây nhầm lẫn hơn nghĩa ở chủ đề
    khác); chủ đề ít từ thì bù thêm từ TOÀN BỘ từ điển để vẫn đủ số lựa chọn
    khi kho từ đủ lớn. Từ điển/chủ đề quá nhỏ (vd môi trường test) thì trả về
    ÍT HƠN count lựa chọn — tốt hơn là ném lỗi giữa lúc người học đang làm bài.
    """
    # topic=None: hàng đợi gộp nhiều chủ đề (SC15) hoặc từ chưa gắn chủ đề
    # nào — bỏ qua nhánh "nhiễu cùng chủ đề", lấy thẳng từ toàn bộ từ điển.
    if topic is None:
        same_topic = []
    else:
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


def get_or_start_progress(user, vocab):
    """Dòng tiến độ của (user, từ); từ học lần đầu thì tạo mới ở giai đoạn NEW."""
    progress, _ = UserVocabularyProgress.objects.get_or_create(
        user=user, vocabulary=vocab, defaults={"card_state": srs.NEW}
    )
    return progress


def _card_of(progress):
    if progress is None:
        return srs.Card()
    return srs.Card(
        state=progress.card_state,
        step=progress.learning_step,
        ease=progress.ease_factor,
        interval_days=progress.interval_days,
        repetitions=progress.srs_level,
    )


def review_word(progress, quality: int, now=None):
    """Chấm một từ, cập nhật lịch ôn tại chỗ. Trả về `srs.Result`.

    Từ đang học (bước theo phút) có `due_at` = bây giờ + vài phút và
    `next_review_date` = hôm nay — nên vẫn được tính là "đến hạn hôm nay" ở
    SC03/SC15. Từ tốt nghiệp sang REVIEW thì `due_at` rỗng, lịch theo ngày.
    """
    now = now or timezone.now()
    result = srs.schedule(_card_of(progress), quality)
    card = result.card

    progress.card_state = card.state
    progress.learning_step = card.step
    progress.ease_factor = card.ease
    progress.interval_days = card.interval_days
    progress.srs_level = card.repetitions
    if quality >= 3:
        progress.correct_count += 1
    else:
        progress.wrong_count += 1

    # "Hôm nay" tính theo múi giờ của NGƯỜI HỌC (User.timezone), không phải
    # TIME_ZONE của server — nếu không, người dùng ở Việt Nam sẽ thấy thẻ đến
    # hạn lệch 2 tiếng so với mốc nửa đêm của họ.
    today = progress.user.local_today()
    if result.in_session:
        progress.due_at = now + result.delay
        progress.next_review_date = today
    else:
        progress.due_at = None
        progress.next_review_date = today + timedelta(days=card.interval_days)
    progress.is_mastered = progress.srs_level >= 5
    progress.save()
    return result


def grade_previews(progress):
    """{quality: (đơn vị, số)} — khoảng cách ôn lại nếu bấm từng nút."""
    card = _card_of(progress)
    return {q: srs.delay_parts(srs.schedule(card, q).delay) for q in srs.GRADES}


# Các cột được chụp lại trước mỗi lần chấm để HOÀN TÁC được.
_SNAPSHOT_FIELDS = (
    "card_state", "learning_step", "ease_factor", "interval_days", "srs_level",
    "correct_count", "wrong_count", "is_mastered",
)


def progress_snapshot(progress):
    """Bản chụp JSON-serializable (cất được vào request.session)."""
    snap = {f: getattr(progress, f) for f in _SNAPSHOT_FIELDS}
    snap["next_review_date"] = (
        progress.next_review_date.isoformat() if progress.next_review_date else None
    )
    snap["due_at"] = progress.due_at.isoformat() if progress.due_at else None
    return snap


def restore_progress(progress, snap):
    for f in _SNAPSHOT_FIELDS:
        setattr(progress, f, snap[f])
    progress.next_review_date = (
        date.fromisoformat(snap["next_review_date"]) if snap["next_review_date"] else None
    )
    progress.due_at = datetime.fromisoformat(snap["due_at"]) if snap["due_at"] else None
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
    unseen = max(0, total - learned)
    # Còn từ chưa học nhưng hôm nay đã hết hạn mức từ mới -> "Học tiếp" sẽ
    # không đưa ra được từ mới nào; trang chủ phải nói rõ và mời "học thêm".
    limit_reached = bool(unseen) and count_new_words_today(user) >= user.daily_review_goal
    return {
        "topic": topic,
        "learned": learned,
        "total": total,
        "percent": round(learned * 100 / total) if total else 0,
        "unseen": unseen,
        "new_limit_reached": limit_reached,
        "extra_count": min(unseen, user.daily_review_goal or 1),
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


# =============================================================================
# Hàng đợi học cho phiên NHIỀU CHỦ ĐỀ (bắt đầu từ SC05 — nút "Bắt đầu học")
# -----------------------------------------------------------------------------
# Khác `get_flashcard_queue` ở chỗ nguồn vào là TẬP TỪ ĐÃ LỌC (nhiều chủ đề,
# có thể kèm từ khoá và trạng thái) chứ không phải một Topic. Thứ tự ưu tiên
# vẫn giữ nguyên tinh thần SRS: đến hạn -> chưa học -> còn lại.
# =============================================================================

# Trần số từ đọc lên để xếp hàng đợi. Người học lọc ra cả nghìn từ vẫn chỉ
# học được vài chục trong một lượt, nên không cần kéo cả kho về Python.
STUDY_SOURCE_CAP = 2000

_BUCKET_DUE = 0      # đến hạn ôn — học trước tiên
_BUCKET_NEW = 1      # chưa học lần nào
_BUCKET_LATER = 2    # đã học nhưng chưa tới hạn — chỉ học khi hai nhóm trên hết


def build_study_queue(user, words, limit=0):
    """Danh sách id từ vựng theo thứ tự học, cắt theo `limit` (0 = không giới hạn).

    `words` là queryset đã qua `apps.vocabulary.selectors.filter_vocabulary()`.
    Trả về LIST ID chứ không phải object vì hàng đợi được cất trong
    `request.session` (phải JSON-serializable) và từ có thể bị sửa/xoá giữa
    chừng — view nạp lại từng từ khi hiển thị.
    """
    ordered_ids = [word.pk for word in words[:STUDY_SOURCE_CAP]]
    if not ordered_ids:
        return []

    today = user.local_today()
    progress_by_id = dict(
        UserVocabularyProgress.objects.filter(
            user=user, vocabulary_id__in=ordered_ids
        ).values_list("vocabulary_id", "next_review_date")
    )

    def sort_key(item):
        index, vocab_id = item
        if vocab_id not in progress_by_id:
            return (_BUCKET_NEW, index, index)
        due_date = progress_by_id[vocab_id]
        if due_date is None:
            # Có tiến độ nhưng chưa được xếp lịch — coi như đến hạn ngay.
            return (_BUCKET_DUE, 0, index)
        if due_date <= today:
            return (_BUCKET_DUE, due_date.toordinal(), index)
        return (_BUCKET_LATER, due_date.toordinal(), index)

    queue = [
        vocab_id
        for _, vocab_id in sorted(enumerate(ordered_ids), key=sort_key)
    ]
    return queue[:limit] if limit else queue


# =============================================================================
# SC15 — Ôn tập
# -----------------------------------------------------------------------------
# Mọi con số ở đây chỉ tính trên NHỮNG TỪ ĐÃ HỌC (có dòng
# UserVocabularyProgress của chính user). Định nghĩa từng phạm vi ôn nằm ở
# `apps.vocabulary.selectors.progress_filter_for_scope()` — dùng chung với
# hàng đợi để con số trên thẻ và số từ thật sự ôn được không lệch nhau.
# =============================================================================

# Ước lượng thời gian một lượt ôn. 20 giây/từ là mức đo được của một thẻ
# flashcard có lật xem nghĩa; chỉ dùng để hiện "khoảng N phút" nên không cần
# chính xác hơn.
SECONDS_PER_WORD = 20

# Ba mốc độ nhớ, cắt theo srs_level. 5 trùng ngưỡng `is_mastered` mà
# `review_word()` đang dùng — đừng đổi rời hai chỗ.
MEMORY_BANDS = (
    ("fresh", "learning.review.band.fresh", 0, 1),
    ("learning", "learning.review.band.learning", 2, 4),
    ("mastered", "learning.review.band.mastered", 5, None),
)


def record_extra_review(progress, quality: int):
    """Ghi nhận một lần ôn THÊM (ngoài lịch) — KHÔNG đụng vào lịch SM-2.

    Dùng cho các phạm vi ở `selectors.SCOPES_WITHOUT_SCHEDULE`: người học chủ
    động ôn sớm từ chưa đến hạn hoặc ôn lại từ đã thuộc. Nếu vẫn gọi
    `review_word()` ở đây thì mỗi lượt ôn sớm lại nhân `interval_days` lên một
    lần nữa, đẩy từ đó ra xa hàng tháng — đúng thứ người học KHÔNG hề yêu cầu
    khi bấm "ôn thêm". Vì vậy chỉ cộng đúng/sai để thống kê "từ hay quên".
    """
    if quality >= 3:
        progress.correct_count += 1
    else:
        progress.wrong_count += 1
    progress.save(update_fields=["correct_count", "wrong_count", "updated_at"])
    return progress


def get_review_overview(user):
    """Khối đầu trang SC15: hàng đợi hôm nay + số liệu tổng, gộp 1 query."""
    from apps.vocabulary import selectors as vocab_selectors

    today = user.local_today()
    upcoming_until = today + timedelta(days=vocab_selectors.UPCOMING_DAYS)
    rows = UserVocabularyProgress.objects.filter(user=user).aggregate(
        studied=Count("pk"),
        mastered=Count("pk", filter=Q(is_mastered=True)),
        overdue=Count("pk", filter=Q(next_review_date__lt=today)),
        due_today=Count(
            "pk",
            filter=Q(next_review_date=today) | Q(next_review_date__isnull=True),
        ),
        upcoming=Count(
            "pk",
            filter=Q(next_review_date__gt=today, next_review_date__lte=upcoming_until),
        ),
        leech=Count(
            "pk",
            filter=Q(
                wrong_count__gt=F("correct_count"),
                wrong_count__gte=vocab_selectors.LEECH_MIN_WRONG,
            ),
        ),
    )
    due_total = rows["overdue"] + rows["due_today"]
    rows["due_total"] = due_total
    # Làm tròn LÊN: 3 từ vẫn là "khoảng 1 phút", không phải 0 phút.
    rows["minutes"] = -(-due_total * SECONDS_PER_WORD // 60)
    rows["overdue_percent"] = round(rows["overdue"] * 100 / due_total) if due_total else 0
    rows["due_today_percent"] = 100 - rows["overdue_percent"] if due_total else 0
    return rows


def get_memory_distribution(user):
    """Ba nhóm độ nhớ, kèm % để vẽ thanh tiến độ."""
    aggregates = {}
    for key, _label_key, low, high in MEMORY_BANDS:
        condition = Q(srs_level__gte=low)
        if high is not None:
            condition &= Q(srs_level__lte=high)
        aggregates[key] = Count("pk", filter=condition)
    rows = UserVocabularyProgress.objects.filter(user=user).aggregate(**aggregates)

    total = sum(rows.values())
    return [
        {
            "key": key,
            "label_key": label_key,
            "count": rows[key],
            "percent": round(rows[key] * 100 / total) if total else 0,
        }
        for key, label_key, _low, _high in MEMORY_BANDS
    ]


def get_review_calendar(user, days=7):
    """Cột "quá hạn" + `days` ngày kể từ hôm nay, mỗi cột kèm % chiều cao.

    Ngày được trả về dạng `date` để template tự định dạng — không nhét tên
    thứ tiếng Việt vào Python (chuỗi hiển thị thuộc về .properties).
    """
    today = user.local_today()
    last_day = today + timedelta(days=days - 1)

    counts = dict(
        UserVocabularyProgress.objects.filter(
            user=user, next_review_date__gte=today, next_review_date__lte=last_day
        )
        .values_list("next_review_date")
        .annotate(n=Count("pk"))
    )
    overdue = UserVocabularyProgress.objects.filter(
        user=user, next_review_date__lt=today
    ).count()
    # Từ có tiến độ nhưng chưa xếp lịch được coi là đến hạn hôm nay ở khắp
    # nơi (build_study_queue, progress_filter_for_scope) — ở đây cũng vậy.
    unscheduled = UserVocabularyProgress.objects.filter(
        user=user, next_review_date__isnull=True
    ).count()

    buckets = [{"date": None, "is_overdue": True, "is_today": False, "count": overdue}]
    for offset in range(days):
        day = today + timedelta(days=offset)
        count = counts.get(day, 0) + (unscheduled if offset == 0 else 0)
        buckets.append(
            {"date": day, "is_overdue": False, "is_today": offset == 0, "count": count}
        )

    peak = max((b["count"] for b in buckets), default=0)
    for bucket in buckets:
        bucket["percent"] = round(bucket["count"] * 100 / peak) if peak else 0
    return buckets


def get_topic_review_rows(user):
    """Bảng "toàn bộ từ đã học" nhóm theo chủ đề — 3 query, không N+1.

    LƯU Ý: một từ thuộc nhiều chủ đề được đếm ở MỌI dòng liên quan, nên tổng
    các dòng có thể lớn hơn tổng số từ đã học. Template có một dòng ghi chú
    việc này — đừng "sửa" bằng cách chia đều cho số chủ đề.
    """
    today = user.local_today()

    totals = dict(
        Topic.objects.annotate(n=Count("vocabularies", distinct=True))
        .values_list("pk", "n")
    )
    progress_rows = (
        UserVocabularyProgress.objects.filter(user=user, vocabulary__topics__isnull=False)
        .values("vocabulary__topics")
        .annotate(
            learned=Count("pk", distinct=True),
            due=Count(
                "pk",
                distinct=True,
                filter=Q(next_review_date__lte=today) | Q(next_review_date__isnull=True),
            ),
        )
    )
    by_topic = {row["vocabulary__topics"]: row for row in progress_rows}

    rows = []
    for topic in Topic.objects.filter(pk__in=by_topic.keys()).order_by("name"):
        row = by_topic[topic.pk]
        total = totals.get(topic.pk, 0)
        rows.append({
            "topic": topic,
            "total": total,
            "learned": row["learned"],
            "due": row["due"],
            "percent": round(row["learned"] * 100 / total) if total else 0,
        })
    # Chủ đề đang nợ nhiều từ đến hạn nhất lên đầu — bảng là để hành động,
    # không phải để tra cứu theo tên.
    rows.sort(key=lambda r: (-r["due"], -r["learned"]))
    return rows
