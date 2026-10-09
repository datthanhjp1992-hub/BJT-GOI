"""
Logic nghiệp vụ của app learning:

1. Lịch ôn tập (`review_word`) — SM-2 có bước học theo phút, xem `srs.py`;
   quality 0-5 quy từ 4 nút Quên/Khó/Nhớ/Dễ. Hàng đợi SC04 (`get_topic_queue`).
2. Số liệu cho SC03_TrangChu (`get_learning_stats`, `get_streak_days`,
   `get_topic_in_progress`, `get_suggested_topics`).
3. Nút "Học hôm nay" của SC03 (`build_daily_queue`, `get_daily_overview`) và
   badge "Ôn tập" ở sidebar (`get_due_badge_count`) — spec.md Phase 3.

View chỉ gọi xuống đây rồi đẩy vào template — không tự viết truy vấn.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.core.cache import cache
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
    """Từ hẹn ôn ngày mai — kể cả từ đang học bị hoãn sang mai (T6.2)."""
    tomorrow = user.local_today() + timedelta(days=1)
    return UserVocabularyProgress.objects.filter(
        user=user, card_state__in=(srs.REVIEW,) + LEFTOVER_STATES, next_review_date=tomorrow
    ).count()


# =============================================================================
# Từ dở bước học (spec.md T6.2, 09/10/2026)
# -----------------------------------------------------------------------------
# Từ LEARNING/RELEARNING còn bước 1-10 phút mà người học rời phiên. Số liệu
# thật: 121 từ kẹt như vậy sau một phiên 143 từ mới, hôm sau thành "quá hạn" và
# bị xếp SAU toàn bộ từ ôn. Ba luật:
#   1. Kết thúc phiên -> `postpone_learning()` hẹn chúng sang MAI
#      (next_review_date = mai, due_at = None), giữ nguyên giai đoạn/bước.
#   2. "Từ dở" = đang học / học lại, đã tới ngày, và lần chấm cuối KHÔNG phải
#      hôm nay (due_at rỗng — vừa hoãn — hoặc trước nửa đêm hôm nay — bỏ ngang
#      phiên). Chúng tính là "đến hạn hôm nay" (không phải quá hạn) và đứng ĐẦU
#      hàng đợi: từ mới nhất, dễ quên nhất.
#   3. Chấm từ dở: "Nhớ" tốt nghiệp luôn (`srs.schedule(overnight=True)`).
# =============================================================================

LEFTOVER_STATES = (srs.LEARNING, srs.RELEARNING)


def _is_leftover_learning(progress, day_start):
    """Từ dở theo luật 2 — KHÔNG xét ngày ôn (nơi gọi tự lọc ngày)."""
    return progress.card_state in LEFTOVER_STATES and (
        progress.due_at is None or progress.due_at < day_start
    )


def leftover_learning_q(user):
    """Điều kiện SQL của "từ dở đến hạn hôm nay" — dùng cho các bộ đếm."""
    return Q(
        card_state__in=LEFTOVER_STATES,
        next_review_date__lte=user.local_today(),
    ) & (Q(due_at__isnull=True) | Q(due_at__lt=local_day_start(user)))


def postpone_learning(user, vocabulary_ids):
    """Hẹn các từ đang học dở trong `vocabulary_ids` sang ngày mai. Trả về số từ.

    Chỉ đụng từ còn ở LEARNING/RELEARNING và đang đến hạn hôm nay — từ đã tốt
    nghiệp hay đã hoãn rồi giữ nguyên. Một câu UPDATE (không qua save() nên tự
    đặt updated_at).
    """
    if not vocabulary_ids:
        return 0
    count = UserVocabularyProgress.objects.filter(
        user=user, vocabulary_id__in=list(vocabulary_ids),
        card_state__in=LEFTOVER_STATES, next_review_date__lte=user.local_today(),
    ).update(
        next_review_date=user.local_today() + timedelta(days=1),
        due_at=None,
        updated_at=timezone.now(),
    )
    if count:
        invalidate_due_badge(user.pk)
    return count


# =============================================================================
# Hạn mức từ mới mỗi ngày — MỘT nguồn cho mọi lối vào (spec.md T6.1)
# -----------------------------------------------------------------------------
# SC03 "Học hôm nay", SC04/SC06 theo chủ đề và SC05 "Bắt đầu học" đều hỏi hàm
# này, không tự tính `goal - count_new_words_today()` nữa. Số liệu thật
# 09/10/2026: SC05 không giới hạn nên có ngày vào 143-147 từ mới (hạn mức 20),
# kéo theo hàng trăm từ cần ôn những ngày sau.
# =============================================================================


@dataclass
class NewWordAllowance:
    goal: int            # User.daily_review_goal — hạn mức TỪ MỚI mỗi ngày
    learned_today: int   # count_new_words_today()
    left: int            # số từ mới còn được học hôm nay (>= 0)
    backlog: int = 0     # số từ đang nợ ôn (T6.5)
    paused: bool = False  # T6.5: hạn mức bị giảm/dừng vì nợ ôn


def new_word_allowance(user):
    goal = user.daily_review_goal
    learned = count_new_words_today(user)
    return NewWordAllowance(goal=goal, learned_today=learned, left=max(0, goal - learned))


def over_limit_forecast(user, extra, allowance=None):
    """Số liệu cho khối "Vẫn học thêm N từ mới" (templates/learning/_over_limit_notice.html).

    Từ mới tốt nghiệp bằng "Nhớ" luôn hẹn sau srs.GRADUATE_INTERVAL = 1 ngày,
    nên học thêm `extra` từ hôm nay ~ ngày mai có thêm `extra` từ cần ôn.
    """
    allowance = allowance or new_word_allowance(user)
    return {
        "learned": allowance.learned_today,
        "goal": allowance.goal,
        "extra": extra,
        "tomorrow": count_due_tomorrow(user) + extra,
    }


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

    1. Từ ĐẾN HẠN ôn (next_review_date <= hôm nay), quá hạn lâu nhất trước.
    2. Từ MỚI theo bảng chữ cái, tối đa `user.daily_review_goal` từ/ngày
       (tính chung mọi chủ đề — xem count_new_words_today).
    3. Từ ĐANG HỌC / HỌC LẠI (bước học tính bằng phút), tới giờ sớm nhất
       trước. Chưa tới giờ thì "học trước" — ahead_minutes cho biết còn bao lâu.

    Từ 01/10/2026 ("hết lượt rồi mới ôn lại"): từ đang học KHÔNG chen lên
    trước từ chưa gặp nữa, dù bước học đã tới giờ. Người học đi trọn một lượt
    các từ đã chọn rồi mới gặp lại những từ bấm Quên/Khó/Nhớ. `due_at` vẫn
    giữ nguyên nên lịch SM-2 không bị ảnh hưởng — từ chỉ được hỏi lại muộn hơn.

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
    day_start = local_day_start(user)

    def due_today(p):
        return p.next_review_date is None or p.next_review_date <= today

    # T6.2: từ đang học bị hoãn sang mai (next_review_date > hôm nay) không
    # xuất hiện hôm nay; từ dở từ hôm trước đứng ĐẦU nhóm đến hạn.
    learning = sorted(
        (
            p for p in progress.values()
            if p.card_state in srs.IN_SESSION_STATES and due_today(p)
            and not _is_leftover_learning(p, day_start)
        ),
        key=lambda p: (p.due_at or now, p.vocabulary_id),
    )
    learn_due = [p for p in learning if (p.due_at or now) <= now]
    learn_ahead = [p for p in learning if (p.due_at or now) > now]
    leftover = sorted(
        (p for p in progress.values() if due_today(p) and _is_leftover_learning(p, day_start)),
        key=lambda p: (p.next_review_date or date.min, p.vocabulary_id),
    )
    review_due = leftover + sorted(
        (p for p in progress.values() if p.card_state == srs.REVIEW and due_today(p)),
        key=lambda p: (p.next_review_date or date.min, p.vocabulary_id),
    )

    allowance = new_word_allowance(user)
    new_limit, new_today, new_left = allowance.goal, allowance.learned_today, allowance.left
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
        [by_id[p.vocabulary_id] for p in review_due if p.vocabulary_id in by_id]
        + new_words
        + [by_id[p.vocabulary_id] for p in learn_due if p.vocabulary_id in by_id]
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


# Số ví dụ câu hiện dưới thẻ (cùng con số với study_view: word.examples.all()[:3]).
CARD_EXAMPLES_MAX = 3


@dataclass
class StudyCard:
    """Một thẻ của bộ thẻ nhúng (spec.md T4.3) — đủ dữ liệu để render thẻ."""
    word: Vocabulary
    progress: "UserVocabularyProgress | None"
    examples: list
    comment_count: int = 0


def get_study_cards(user, vocabulary_ids):
    """Các thẻ của `vocabulary_ids` theo ĐÚNG thứ tự truyền vào, số query cố
    định (không tăng theo số thẻ): từ + chủ đề + ví dụ, tiến độ của user, số
    bình luận. Id của từ đã bị xoá thì không có trong kết quả."""
    from apps.gamification import services as gamification_services

    ids = list(dict.fromkeys(vocabulary_ids))
    if not ids:
        return []
    words = Vocabulary.objects.filter(pk__in=ids).prefetch_related("topics", "examples").in_bulk()
    progress = {
        p.vocabulary_id: p
        for p in UserVocabularyProgress.objects.filter(user=user, vocabulary_id__in=ids)
    }
    comments = gamification_services.count_vocabulary_comments(ids)
    cards = []
    for vid in ids:
        word = words.get(vid)
        if word is None:
            continue
        examples = sorted(word.examples.all(), key=lambda ex: ex.pk)[:CARD_EXAMPLES_MAX]
        cards.append(StudyCard(word, progress.get(vid), examples, comments.get(vid, 0)))
    return cards


def get_or_start_progress(user, vocab):
    """Dòng tiến độ của (user, từ); từ học lần đầu thì tạo mới ở giai đoạn NEW."""
    progress, _ = UserVocabularyProgress.objects.get_or_create(
        user=user, vocabulary=vocab, defaults={"card_state": srs.NEW}
    )
    return progress


def _overnight(progress):
    """Từ dở từ hôm trước? -> "Nhớ" tốt nghiệp luôn (T6.2 luật 3)."""
    if progress is None or progress.card_state not in LEFTOVER_STATES:
        return False
    return _is_leftover_learning(progress, local_day_start(progress.user))


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
    result = srs.schedule(_card_of(progress), quality, overnight=_overnight(progress))
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
    invalidate_due_badge(progress.user_id)
    return result


def grade_previews(progress):
    """{quality: (đơn vị, số)} — khoảng cách ôn lại nếu bấm từng nút."""
    card, overnight = _card_of(progress), _overnight(progress)
    return {
        q: srs.delay_parts(srs.schedule(card, q, overnight=overnight).delay)
        for q in srs.GRADES
    }


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
    invalidate_due_badge(progress.user_id)
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
    """Chủ đề user đang học dở, kèm tiến độ.

    Ưu tiên chủ đề của PHIÊN HỌC gần nhất (đúng nghĩa "đang học dở"); chưa
    có phiên nào thì lấy chủ đề mà user có nhiều từ đang theo dõi nhất.
    Trả None nếu user chưa động vào chủ đề nào.

    Từ 03/10/2026 (spec.md T3.1 c) trang chủ không còn khối "Học tiếp" —
    `build_daily_queue` dùng chủ đề này làm nguồn từ mới đầu tiên.
    """
    topic = _topic_in_progress(user)
    if topic is None:
        return None

    total = topic.vocabularies.count()
    learned = UserVocabularyProgress.objects.filter(
        user=user, vocabulary__topics=topic
    ).count()
    unseen = max(0, total - learned)
    # Còn từ chưa học nhưng hôm nay đã hết hạn mức từ mới -> "Học tiếp" sẽ
    # không đưa ra được từ mới nào; trang chủ phải nói rõ và mời "học thêm".
    limit_reached = bool(unseen) and new_word_allowance(user).left == 0
    return {
        "topic": topic,
        "learned": learned,
        "total": total,
        "percent": round(learned * 100 / total) if total else 0,
        "unseen": unseen,
        "new_limit_reached": limit_reached,
        "extra_count": min(unseen, user.daily_review_goal or 1),
    }


def _topic_in_progress(user):
    """Chỉ riêng Topic của `get_topic_in_progress()` — không đếm tiến độ."""
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
    return topic


def get_startable_topics():
    """Chủ đề có từ, kèm `word_count`, nhiều từ nhất trước — nguồn của mục
    "Chủ đề gợi ý" (SC03) và lưới chọn chủ đề ở màn hướng dẫn lần đầu."""
    return (
        Topic.objects.annotate(word_count=Count("vocabularies", distinct=True))
        .filter(word_count__gt=0)
        .order_by("-word_count", "name")
    )


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

    base = get_startable_topics()
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


@dataclass
class StudyPlan:
    queue: list              # id từ vựng theo thứ tự học
    held_new: int = 0        # từ mới LẼ RA vào hàng đợi nhưng bị giữ lại vì hạn mức


def build_study_queue(user, words, limit=0):
    """Danh sách id từ vựng theo thứ tự học, cắt theo `limit` (0 = không giới hạn).

    `words` là queryset đã qua `apps.vocabulary.selectors.filter_vocabulary()`.
    Trả về LIST ID chứ không phải object vì hàng đợi được cất trong
    `request.session` (phải JSON-serializable) và từ có thể bị sửa/xoá giữa
    chừng — view nạp lại từng từ khi hiển thị.

    Không giới hạn từ mới — dùng cho SC15 (chỉ có từ đã học). SC05 đi qua
    `plan_study_queue(new_limit=...)`.
    """
    return plan_study_queue(user, words, limit=limit).queue


def plan_study_queue(user, words, limit=0, new_limit=None):
    """Như `build_study_queue` nhưng giữ lại từ mới vượt `new_limit` (spec.md T6.1).

    Từ mới vượt hạn mức bị BỎ khỏi hàng đợi (không dời xuống cuối), từ đến hạn
    và từ đã học giữ nguyên. `held_new` chỉ đếm những từ mới mà không có hạn
    mức thì đã lọt vào lượt học (sau khi cắt `limit`) — để thông báo đúng con
    số người học bị "mất".
    """
    ordered = _order_study_ids(user, words)
    cut = (lambda ids: ids[:limit]) if limit else (lambda ids: ids)
    if new_limit is None:
        return StudyPlan(cut([vid for _, vid in ordered]))

    capped, taken = [], 0
    for bucket, vid in ordered:
        if bucket == _BUCKET_NEW:
            if taken >= new_limit:
                continue
            taken += 1
        capped.append(vid)
    new_ids = {vid for bucket, vid in ordered if bucket == _BUCKET_NEW}
    uncapped_new = sum(1 for vid in cut([vid for _, vid in ordered]) if vid in new_ids)
    capped = cut(capped)
    return StudyPlan(capped, uncapped_new - sum(1 for vid in capped if vid in new_ids))


def _order_study_ids(user, words):
    """[(nhóm, id)] theo thứ tự học: đến hạn -> chưa học -> chưa tới hạn."""
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

    return [
        (sort_key(item)[0], item[1])
        for item in sorted(enumerate(ordered_ids), key=sort_key)
    ]


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
    # Từ dở bước học (T6.2) bỏ ngang từ hôm trước tính là "đến hạn hôm nay",
    # không phải "quá hạn".
    leftover = leftover_learning_q(user)
    rows = UserVocabularyProgress.objects.filter(user=user).aggregate(
        studied=Count("pk"),
        mastered=Count("pk", filter=Q(is_mastered=True)),
        overdue=Count("pk", filter=Q(next_review_date__lt=today) & ~leftover),
        due_today=Count(
            "pk",
            filter=Q(next_review_date=today) | Q(next_review_date__isnull=True) | leftover,
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
    # Từ có tiến độ nhưng chưa xếp lịch, và từ dở bước học bỏ ngang từ hôm
    # trước (T6.2), được coi là đến hạn hôm nay ở khắp nơi — ở đây cũng vậy.
    leftover = leftover_learning_q(user)
    past = UserVocabularyProgress.objects.filter(user=user).aggregate(
        overdue=Count("pk", filter=Q(next_review_date__lt=today) & ~leftover),
        unscheduled=Count(
            "pk", filter=Q(next_review_date__isnull=True) | (Q(next_review_date__lt=today) & leftover)
        ),
    )
    overdue, unscheduled = past["overdue"], past["unscheduled"]

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


# =============================================================================
# "Học hôm nay" — nút chính của SC03 (spec.md T3.1, Dat duyệt 02/10/2026)
# -----------------------------------------------------------------------------
# Một hàng đợi gom MỌI chủ đề, rồi đi qua đúng luồng study_* như SC05/SC15
# (không có luồng học thứ tư):
#   1. Từ đến hạn ôn (REVIEW, next_review_date <= hôm nay), quá hạn lâu nhất
#      trước; tiếp theo là từ đang ở bước học (quên/chưa qua hết bước).
#   2. Từ mới, tối đa `daily_review_goal - count_new_words_today()`, lấy từ
#      chủ đề đang học dở trước, hết thì sang chủ đề gợi ý — không trộn ngẫu
#      nhiên. Hoàn tác lần chấm đầu của từ mới xoá dòng tiến độ, nên hạn mức
#      tự lùi lại mà không cần sổ sách riêng.
# =============================================================================

# Số chủ đề gợi ý xét thêm khi chủ đề đang học dở đã hết từ mới. Mỗi chủ đề
# tốn 1 query và vòng lặp dừng ngay khi đủ hạn mức, nên đặt rộng tay được.
DAILY_NEW_TOPIC_LOOKAHEAD = 10


def _daily_due_ids(user):
    """Id từ cần ôn hôm nay ở mọi chủ đề: từ dở (T6.2) -> đến hạn -> đang học."""
    today = user.local_today()
    day_start = local_day_start(user)
    # Chưa xếp lịch (next_review_date rỗng) = đến hạn ngay, như build_study_queue.
    # Từ đang học bị hoãn sang mai (next_review_date > hôm nay) không vào.
    rows = UserVocabularyProgress.objects.filter(user=user).filter(
        Q(next_review_date__lte=today) | Q(next_review_date__isnull=True),
        card_state__in=(srs.REVIEW,) + srs.IN_SESSION_STATES,
    ).values_list("vocabulary_id", "card_state", "next_review_date", "due_at")

    leftover, review, learning = [], [], []
    for vocab_id, state, review_date, due_at in rows:
        if state == srs.REVIEW:
            review.append(((review_date or date.min), vocab_id))
        elif state in LEFTOVER_STATES and (due_at is None or due_at < day_start):
            leftover.append(((review_date or date.min), vocab_id))
        else:
            learning.append(((due_at or timezone.now()), vocab_id))
    return [vid for _, vid in sorted(leftover) + sorted(review)] + [vid for _, vid in sorted(learning)]


def _daily_new_ids(user, count):
    """Tối đa `count` id từ mới: chủ đề đang học dở trước, rồi chủ đề gợi ý."""
    if count <= 0:
        return []
    topics = []
    first = _topic_in_progress(user)
    if first is not None:
        topics.append(first)
    topics += [
        topic for topic in get_suggested_topics(user, limit=DAILY_NEW_TOPIC_LOOKAHEAD)
        if topic not in topics
    ]

    picked = []
    for topic in topics:
        rest = count - len(picked)
        if rest <= 0:
            break
        # Một từ có thể thuộc nhiều chủ đề — đừng lấy trùng.
        picked += list(
            Vocabulary.objects.filter(topics=topic)
            .exclude(progress__user=user)
            .exclude(pk__in=picked)
            .order_by("word")
            .values_list("pk", flat=True)[:rest]
        )
    return picked


def _daily_parts(user):
    due = _daily_due_ids(user)[:STUDY_SOURCE_CAP]
    return due, _daily_new_ids(user, new_word_allowance(user).left)


def build_daily_queue(user):
    """Hàng đợi "Học hôm nay" (list id, cất được vào request.session)."""
    due, new = _daily_parts(user)
    return due + new


def get_daily_overview(user):
    """Con số trên nút "Học hôm nay": {due, new, total, minutes, due_tomorrow}.

    `due_tomorrow` chỉ tính khi hôm nay đã xong (total == 0) — đó là lúc trang
    chủ cần nói "mai có N từ"; còn việc thì khỏi tốn thêm query.
    """
    due, new = _daily_parts(user)
    total = len(due) + len(new)
    return {
        "due": len(due),
        "new": len(new),
        "total": total,
        # Làm tròn LÊN như get_review_overview(): 3 từ vẫn là "khoảng 1 phút".
        "minutes": -(-total * SECONDS_PER_WORD // 60),
        "due_tomorrow": count_due_tomorrow(user) if total == 0 else 0,
    }


# =============================================================================
# Badge "Ôn tập" ở sidebar (spec.md T3.4) — xem apps/learning/context_processors.py
# -----------------------------------------------------------------------------
# Cùng định nghĩa "đến hạn" với SC15 (get_review_overview().due_total): ngày ôn
# <= hôm nay, hoặc chưa xếp lịch. Cache 60 giây/user để không tốn 1 query mỗi
# trang; giá trị kèm NGÀY của user nên qua nửa đêm là tự tính lại.
# =============================================================================

DUE_BADGE_TTL_SECONDS = 60


def _due_badge_key(user_id):
    return f"learning:due_badge:{user_id}"


def count_due_today(user):
    today = user.local_today()
    return UserVocabularyProgress.objects.filter(
        Q(next_review_date__lte=today) | Q(next_review_date__isnull=True), user=user,
    ).count()


def get_due_badge_count(user):
    today = user.local_today().isoformat()
    cached = cache.get(_due_badge_key(user.pk))
    if cached and cached[0] == today:
        return cached[1]
    count = count_due_today(user)
    cache.set(_due_badge_key(user.pk), (today, count), DUE_BADGE_TTL_SECONDS)
    return count


def invalidate_due_badge(user_id):
    """Gọi sau mỗi lần lịch ôn của user đổi (chấm / hoàn tác)."""
    cache.delete(_due_badge_key(user_id))
