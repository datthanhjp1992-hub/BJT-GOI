"""
View của app learning: SC03 Trang chủ · SC04 Flashcard · SC06 Kiểm tra ·
SC15 Ôn tập.

Flow ôn tập (26/09/2026, kiểu Anki — xem apps/learning/srs.py):
  * Bấm "Quên"/"Khó" với từ mới hoặc từ đang học -> từ quay lại sau vài phút
    NGAY TRONG PHIÊN, nhớ được qua hết các bước mới xếp lịch theo ngày.
  * SC04 giới hạn từ mới theo `User.daily_review_goal` mỗi ngày.
  * Mỗi lần chấm có thể HOÀN TÁC (`undo_view`), hết phiên có màn tổng kết.

Mọi truy vấn thống kê nằm ở `apps.learning.services`; view chỉ lắp context.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.constants import SESSION_TYPE_FLASHCARD, SESSION_TYPE_QUIZ
from apps.core.properties import label, message
from apps.gamification.models import Contribution
from apps.gamification import services as gamification_services
from apps.gamification.services import CONTRIBUTION_TYPE_COMMENT, STATUS_APPROVED
from apps.vocabulary import selectors as vocab_selectors
from apps.vocabulary.models import Topic, Vocabulary

from . import services, srs
from .models import StudySession, UserVocabularyProgress, UserWordlist
from .services import QUALITY_MAP, record_extra_review, review_word


@login_required
def dashboard_view(request):
    """SC03_TrangChu."""
    user = request.user
    stats = services.get_learning_stats(user)
    context = {
        "greeting_key": services.get_greeting_label_key(user),
        "display_name": (user.first_name or "").strip() or user.get_username(),
        "stats": stats,
        "due_count": stats["due_today"],
        "in_progress": services.get_topic_in_progress(user),
        "suggested_topics": services.get_suggested_topics(user),
        "active_nav": "home",
    }
    return render(request, "learning/dashboard.html", context)


def _flashcard_session_keys(topic_slug):
    """Hai khoá trong request.session để nhớ TỔNG số thẻ và bản ghi
    StudySession của phiên flashcard đang chạy cho 1 chủ đề. Khoá theo
    topic_slug nên user học nhiều chủ đề (tab khác nhau) không đụng nhau.

    (Khoá "total" không còn dùng từ khi có bước học — tổng số thẻ giờ tính
    lại mỗi lần từ số lượt đã chấm + số từ còn lại — nhưng vẫn giữ để dọn
    session cũ của người dùng.)"""
    return f"flashcard_total_{topic_slug}", f"flashcard_session_id_{topic_slug}"


def _close_study_session(request, session_id_key):
    """Đóng StudySession đang mở (nếu có) khi hàng đợi đã hết, để lại mốc
    ended_at cho lịch sử/streak sau này biết phiên kết thúc lúc nào. Trả về
    bản ghi đã đóng (hoặc None) để nơi gọi dựng thông báo tóm tắt nếu cần
    (vd quiz_view hiện điểm số đúng/tổng)."""
    session_id = request.session.pop(session_id_key, None)
    if not session_id:
        return None
    session = StudySession.objects.filter(pk=session_id).first()
    if session and session.ended_at is None:
        session.ended_at = timezone.now()
        session.save(update_fields=["ended_at"])
    return session


def _close_flashcard_session(request, session_id_key):
    _close_study_session(request, session_id_key)


def _ensure_open_session(request, session_id_key, topic, session_type):
    """StudySession đang mở của phiên theo chủ đề; chưa có thì mở mới.

    Phiên mở từ HÔM TRƯỚC (người học để tab qua đêm) bị đóng và thay bằng
    phiên mới — nếu không, lượt học hôm nay bị ghi vào phiên hôm qua và
    streak (tính theo started_at) không nhận ra hôm nay có học.
    """
    session_id = request.session.get(session_id_key)
    session = None
    if session_id:
        session = StudySession.objects.filter(
            pk=session_id, user=request.user, ended_at__isnull=True,
            started_at__gte=services.local_day_start(request.user),
        ).first()
        if session is None:
            _close_study_session(request, session_id_key)
    if session is None:
        session = StudySession.objects.create(
            user=request.user, topic=topic, session_type=session_type,
            started_at=timezone.now(),
        )
        request.session[session_id_key] = session.pk
    return session


# =============================================================================
# Chấm điểm + HOÀN TÁC (dùng chung cho mọi lối vào)
# -----------------------------------------------------------------------------
# Trước mỗi lần chấm, bản chụp tiến độ của từ được đẩy vào một ngăn xếp trong
# request.session (tối đa UNDO_MAX mục). Nút "Hoàn tác" lấy mục trên cùng ra,
# trả tiến độ + bộ đếm StudySession về như cũ rồi hiện lại đúng từ đó.
# Không cần bảng log: từ học lần đầu có bản chụp None -> hoàn tác là xoá dòng
# tiến độ, nên `services.count_new_words_today()` cũng tự lùi lại.
# =============================================================================

UNDO_KEY = "learning_undo"
UNDO_MAX = 20
# {"vocab": id, "flow": "topic:<slug>" | "study"} — từ vừa hoàn tác phải hiện
# lại NGAY ở đúng màn đó, trước mọi từ khác trong hàng đợi.
FORCE_KEY = "learning_force_word"


def _topic_flow(topic_slug):
    return f"topic:{topic_slug}"


FLOW_STUDY = "study"


def _grade(request, vocab, quality, *, flow, session_id=None, touch_schedule=True, extra=None):
    """Chấm một từ, cộng vào StudySession và ghi mục hoàn tác.

    Trả về `srs.Result` (None nếu là lượt "ôn thêm" không đụng lịch).
    """
    user = request.user
    existing = UserVocabularyProgress.objects.filter(user=user, vocabulary=vocab).first()
    snapshot = services.progress_snapshot(existing) if existing else None
    progress = existing or services.get_or_start_progress(user, vocab)

    if touch_schedule:
        result = review_word(progress, quality)
    else:
        record_extra_review(progress, quality)
        result = None

    # quality >= 3 ("Khó"/"Nhớ"/"Dễ") tính là nhớ đúng, khớp ngưỡng SM-2.
    correct = 1 if quality >= 3 else 0
    if session_id:
        StudySession.objects.filter(pk=session_id).update(
            words_reviewed=F("words_reviewed") + 1,
            correct_answers=F("correct_answers") + correct,
        )

    entry = {
        "vocab": vocab.pk,
        "word": vocab.word,
        "snap": snapshot,
        "sid": session_id,
        "correct": correct,
        "day": user.local_today().isoformat(),
        "flow": flow,
    }
    entry.update(extra or {})
    stack = list(request.session.get(UNDO_KEY) or [])[-(UNDO_MAX - 1):]
    stack.append(entry)
    request.session[UNDO_KEY] = stack
    request.session.pop(FORCE_KEY, None)
    return result


def _last_undo(request, flow):
    """Mục hoàn tác trên cùng nếu nó thuộc đúng màn `flow` và là của hôm nay."""
    stack = request.session.get(UNDO_KEY) or []
    if not stack:
        return None
    entry = stack[-1]
    if entry.get("flow") != flow or entry.get("day") != request.user.local_today().isoformat():
        return None
    return entry


def _forced_word(request, flow):
    forced = request.session.get(FORCE_KEY)
    if not forced or forced.get("flow") != flow:
        return None
    word = Vocabulary.objects.filter(pk=forced.get("vocab")).first()
    if word is None:
        request.session.pop(FORCE_KEY, None)
    return word


def _delay_text(parts):
    unit, value = parts
    if isinstance(value, float):
        value = f"{value:g}".replace(".", ",")
    return message(f"learning.flashcard.delay.{unit}", n=value)


# Bốn nút chấm: (mã POST, key nhãn, style nền/chữ — giữ nguyên màu cũ của SC04).
GRADE_BUTTONS = (
    ("quen", "learning.flashcard.button.forgot", "background:#e8c4b8;color:#8f3323;", False),
    ("kho", "learning.flashcard.button.hard", "background:#f0e0c4;color:#8a6a1a;", False),
    ("nho", "learning.flashcard.button.good", "background:#dbe6d8;color:#2f4f47;", False),
    ("de", "learning.flashcard.button.easy", "", True),
)


def _card_context(request, word, *, flow, show_preview=True):
    """Phần context mô tả THẺ đang hiện: giai đoạn, 4 nút kèm khoảng cách, hoàn tác."""
    progress = UserVocabularyProgress.objects.filter(user=request.user, vocabulary=word).first()
    state = progress.card_state if progress else srs.NEW
    previews = services.grade_previews(progress) if show_preview else {}
    buttons = [
        {
            "code": code,
            "label_key": label_key,
            "style": style,
            "primary": primary,
            "delay": _delay_text(previews[QUALITY_MAP[code]]) if previews else "",
        }
        for code, label_key, style, primary in GRADE_BUTTONS
    ]
    undo = _last_undo(request, flow)
    return {
        "card_state": state,
        "card_state_key": f"learning.flashcard.state.{state}",
        "grade_buttons": buttons,
        "undo_word": undo["word"] if undo else "",
    }


def _session_summary(session):
    """Tổng kết một phiên đã đóng — hiện trên màn "đã ôn xong"."""
    if session is None or not session.words_reviewed:
        return None
    again = session.words_reviewed - session.correct_answers
    return {
        "reviewed": session.words_reviewed,
        "correct": session.correct_answers,
        "again": again,
        "percent": round(session.correct_answers * 100 / session.words_reviewed),
    }


def _progress_numbers(done, remaining):
    total = done + remaining
    return {
        "position": done + 1,
        "total": total,
        "percent": round(done * 100 / total) if total else 0,
    }


@login_required
def flashcard_view(request, topic_slug):
    """SC04_HocTuVung — 1 thẻ mỗi lần, theo flow ôn tập của
    `services.get_topic_queue`: từ đang học tới giờ -> từ đến hạn -> từ mới
    (tối đa `daily_review_goal`/ngày) -> học trước từ đang học chưa tới giờ."""
    topic = get_object_or_404(Topic, slug=topic_slug)
    total_key, session_id_key = _flashcard_session_keys(topic.slug)
    flow = _topic_flow(topic.slug)
    queue = services.get_topic_queue(request.user, topic)
    forced = _forced_word(request, flow)
    word = forced or (queue.words[0] if queue.words else None)

    if word is None:
        # Hết thẻ cần ôn (hoặc chủ đề chưa có từ nào) — đóng phiên đang mở và
        # dọn khoá session để lần mở lại sau tính là một lượt ôn mới.
        session = _close_study_session(request, session_id_key)
        request.session.pop(total_key, None)
        undo = _last_undo(request, flow)
        return render(request, "learning/flashcard.html", {
            "topic": topic, "word": None, "scope_label": topic.display_name,
            "summary": _session_summary(session),
            "queue": queue,
            "due_tomorrow": services.count_due_tomorrow(request.user),
            "undo_word": undo["word"] if undo else "",
        })

    session = _ensure_open_session(request, session_id_key, topic, SESSION_TYPE_FLASHCARD)
    session.refresh_from_db(fields=["words_reviewed"])
    remaining = queue.remaining + (1 if forced and forced not in queue.words else 0)

    context = {
        "topic": topic,
        "word": word,
        **_progress_numbers(session.words_reviewed, remaining),
        "queue": queue,
        "ahead_minutes": 0 if forced else queue.ahead_minutes,
        # Ba khoá dưới đây để flashcard.html dùng được cho CẢ HAI lối vào:
        # học theo 1 chủ đề (màn này) và học theo bộ lọc của SC05 (study_view).
        "scope_label": topic.display_name,
        "review_action": reverse("learning:flashcard_review", args=[word.pk]),
        "topic_slug_value": topic.slug,
        "examples": word.examples.all()[:3],
        "comments": Contribution.objects.filter(
            target_vocabulary=word,
            contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            status_code=STATUS_APPROVED,
        ).order_by("-created_at"),
        **_card_context(request, word, flow=flow),
    }
    return render(request, "learning/flashcard.html", context)


@login_required
@require_POST
def flashcard_review(request, vocabulary_id):
    """Endpoint POST của 4 nút Quên/Khó/Nhớ/Dễ trên màn flashcard."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    topic_slug = request.POST.get("topic_slug", "")
    quality = QUALITY_MAP.get(request.POST.get("quality"), 3)

    _, session_id_key = _flashcard_session_keys(topic_slug)
    _grade(
        request, vocab, quality,
        flow=_topic_flow(topic_slug),
        session_id=request.session.get(session_id_key),
        extra={"topic": topic_slug},
    )
    return redirect("learning:flashcard", topic_slug=topic_slug)


@login_required
@require_POST
def undo_view(request):
    """Nút "Hoàn tác" — trả lần chấm gần nhất (của hôm nay) về như cũ."""
    stack = list(request.session.get(UNDO_KEY) or [])
    today = request.user.local_today().isoformat()
    if not stack or stack[-1].get("day") != today:
        flash.info(request, message("learning.flashcard.error.nothing_to_undo"))
        return redirect("learning:dashboard")

    entry = stack.pop()
    request.session[UNDO_KEY] = stack
    vocab_id = entry["vocab"]

    progress = UserVocabularyProgress.objects.filter(
        user=request.user, vocabulary_id=vocab_id
    ).first()
    if entry["snap"] is None:
        if progress is not None:
            progress.delete()
    elif progress is not None:
        services.restore_progress(progress, entry["snap"])

    # Trừ lại bộ đếm của phiên và MỞ LẠI phiên nếu nó vừa bị đóng vì hết thẻ
    # (lần chấm cuối cùng của phiên là lần hay bấm nhầm nhất).
    session = None
    if entry.get("sid"):
        session = StudySession.objects.filter(pk=entry["sid"], user=request.user).first()
    if session is not None:
        session.words_reviewed = max(0, session.words_reviewed - 1)
        session.correct_answers = max(0, session.correct_answers - entry.get("correct", 0))
        session.ended_at = None
        session.save(update_fields=["words_reviewed", "correct_answers", "ended_at"])

    flow = entry.get("flow", "")
    request.session[FORCE_KEY] = {"vocab": vocab_id, "flow": flow}
    flash.info(request, message("learning.flashcard.success.undone", word=entry.get("word", "")))

    if flow == FLOW_STUDY:
        _restore_study_state(request, entry, session)
        return redirect("learning:study")
    topic_slug = entry.get("topic", "")
    if topic_slug and Topic.objects.filter(slug=topic_slug).exists():
        if session is not None:
            _, session_id_key = _flashcard_session_keys(topic_slug)
            request.session[session_id_key] = session.pk
        return redirect("learning:flashcard", topic_slug=topic_slug)
    request.session.pop(FORCE_KEY, None)
    return redirect("learning:dashboard")


@login_required
@require_POST
def flashcard_comment(request, vocabulary_id):
    """Gửi bình luận cho 1 từ ngay trên màn flashcard — tạo Contribution loại
    'Bình luận', trạng thái mặc định 'Chờ duyệt' (SC12 hòm thư sẽ có màn duyệt,
    chưa dựng UI). Bình luận đã duyệt mới hiện công khai ở flashcard_view."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    topic_slug = request.POST.get("topic_slug", "")
    text = (request.POST.get("comment_text") or "").strip()

    if text:
        # Đi qua service chung của SC11 thay vì Contribution.objects.create()
        # thẳng, để hai đường gửi bình luận (màn góp ý và ô nhanh ở đây) không
        # lệch nhau về trạng thái/điểm khi luật thay đổi.
        gamification_services.submit_contribution(
            request.user,
            CONTRIBUTION_TYPE_COMMENT,
            target_vocabulary=vocab,
            comment_text=text,
        )
        flash.success(request, message("learning.flashcard.success.comment_submitted"))
    else:
        flash.error(request, message("common.validation.required"))
    # topic_slug rỗng = bình luận gửi từ phiên học theo bộ lọc (SC05) — quay
    # về đúng màn đó thay vì reverse một route bắt buộc phải có slug.
    if not topic_slug:
        return redirect("learning:study")
    return redirect("learning:flashcard", topic_slug=topic_slug)


def _quiz_session_keys(topic_slug):
    """Giống `_flashcard_session_keys` nhưng khoá riêng namespace "quiz_" —
    user có thể mở song song flashcard và quiz của CÙNG một chủ đề (hai tab)
    mà không đụng phiên của nhau."""
    return f"quiz_total_{topic_slug}", f"quiz_session_id_{topic_slug}"


@login_required
def quiz_view(request, topic_slug):
    """SC06_KiemTra — trắc nghiệm 4 đáp án, dùng CHUNG hàng đợi với SC04
    (`services.get_topic_queue`): từ đang học tới giờ -> từ đến hạn -> từ mới.
    Bấm thẳng vào 1 đáp án là nộp câu đó luôn (xem `quiz_answer_view`) —
    không có bước "xác nhận" riêng như mockup tĩnh, cùng ngôn ngữ thiết kế
    với 4 nút Quên/Khó/Nhớ/Dễ ở SC04."""
    topic = get_object_or_404(Topic, slug=topic_slug)
    total_key, session_id_key = _quiz_session_keys(topic.slug)
    queue = services.get_topic_queue(request.user, topic)

    if not queue.words:
        # Hết từ cần kiểm tra — đóng phiên đang mở và báo điểm số nếu phiên
        # đó thật sự có câu nào được trả lời (tránh flash "0/0" khi user mới
        # mở màn lần đầu mà chủ đề đã hết hạn ôn sẵn từ trước).
        session = _close_study_session(request, session_id_key)
        request.session.pop(total_key, None)
        if session and session.words_reviewed:
            flash.success(request, message(
                "learning.quiz.success.session_complete",
                correct=session.correct_answers, total=session.words_reviewed,
            ))
        return render(request, "learning/quiz.html", {
            "topic": topic, "word": None, "scope_label": topic.display_name,
        })

    session = _ensure_open_session(request, session_id_key, topic, SESSION_TYPE_QUIZ)
    session.refresh_from_db(fields=["words_reviewed"])
    word = queue.words[0]

    context = {
        "topic": topic,
        "word": word,
        **_progress_numbers(session.words_reviewed, queue.remaining),
        "choices": services.get_quiz_choices(word, topic),
        "scope_label": topic.display_name,
        "answer_action": reverse("learning:quiz_answer", args=[topic.slug, word.pk]),
    }
    return render(request, "learning/quiz.html", context)


@login_required
@require_POST
def quiz_answer_view(request, topic_slug, vocabulary_id):
    """Nộp 1 câu trắc nghiệm — mỗi nút đáp án ở quiz.html POST thẳng vào đây.
    Đúng/sai quy đổi sang quality SM-2 (4 = nhớ tốt, 0 = quên) rồi dùng lại
    NGUYÊN `review_word()` của SC04 — quiz và flashcard cùng một cơ chế SRS
    (trả lời sai thì từ quay lại sau vài phút trong cùng lượt)."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    is_correct = request.POST.get("choice") == str(vocab.pk)
    quality = 4 if is_correct else 0

    _, session_id_key = _quiz_session_keys(topic_slug)
    _grade(
        request, vocab, quality,
        flow=f"quiz:{topic_slug}",
        session_id=request.session.get(session_id_key),
        extra={"topic": topic_slug},
    )

    if is_correct:
        flash.success(request, message("learning.quiz.feedback.correct"))
    else:
        flash.error(request, message("learning.quiz.feedback.wrong", meaning=vocab.meaning_vi))
    return redirect("learning:quiz", topic_slug=topic_slug)


# =============================================================================
# Phiên học theo BỘ LỌC (bắt đầu từ nút "Bắt đầu học" ở SC05)
# -----------------------------------------------------------------------------
# Khác flashcard_view ở đúng một điểm: hàng đợi không suy ra từ một Topic mà
# được CHỐT LẠI ngay lúc bấm nút và cất trong request.session. Nhờ vậy người
# học không bị đổi danh sách giữa chừng khi vừa ôn xong một từ (từ đó rời khỏi
# nhóm "đến hạn" và hàng đợi tính lại sẽ ngắn đi bất thường).
# =============================================================================

STUDY_QUEUE_KEY = "study_queue"
STUDY_TOTAL_KEY = "study_total"
STUDY_SESSION_ID_KEY = "study_session_id"
STUDY_SCOPE_KEY = "study_scope"
# Phiên này có được đẩy lịch SM-2 không. False = "ôn thêm" ngoài lịch
# (SC15, xem apps.vocabulary.selectors.SCOPES_WITHOUT_SCHEDULE).
STUDY_TOUCH_SCHEDULE_KEY = "study_touch_schedule"
# Flashcard hay trắc nghiệm — quyết định màn nào hiển thị hàng đợi.
STUDY_MODE_KEY = "study_mode"
# Id các từ của phiên đang ở BƯỚC HỌC (quên / chưa qua hết bước) — chúng rời
# STUDY_QUEUE_KEY nhưng phải quay lại sau vài phút, trước khi phiên kết thúc.
STUDY_LEARNING_KEY = "study_learning"


def _clear_study_session(request):
    request.session.pop(STUDY_QUEUE_KEY, None)
    request.session.pop(STUDY_TOTAL_KEY, None)
    request.session.pop(STUDY_SCOPE_KEY, None)
    request.session.pop(STUDY_TOUCH_SCHEDULE_KEY, None)
    request.session.pop(STUDY_MODE_KEY, None)
    request.session.pop(STUDY_LEARNING_KEY, None)
    return _close_study_session(request, STUDY_SESSION_ID_KEY)


def _touches_schedule(request):
    """Phiên đang mở có cập nhật lịch SM-2 không (mặc định: CÓ).

    Mặc định phải là True để mọi phiên cũ đang nằm trong session của người
    dùng (bắt đầu từ SC05 trước khi có SC15) vẫn chấm điểm như trước.
    """
    return request.session.get(STUDY_TOUCH_SCHEDULE_KEY, True)


def _grade_word(request, vocab, quality):
    """Chấm một từ của phiên theo hàng đợi, tôn trọng cờ "ôn thêm".

    * Phiên chính thức: từ còn ở bước học (quên / chưa qua hết bước) chuyển
      sang STUDY_LEARNING_KEY để quay lại sau vài phút; tốt nghiệp thì rời hẳn.
    * Phiên ôn thêm: không đụng lịch; bấm "Quên" thì từ được đưa xuống CUỐI
      hàng đợi để gặp lại một lần nữa trong lượt này.
    """
    touch = _touches_schedule(request)
    queue = list(request.session.get(STUDY_QUEUE_KEY) or [])
    learning = list(request.session.get(STUDY_LEARNING_KEY) or [])
    in_queue, in_learning = vocab.pk in queue, vocab.pk in learning

    result = _grade(
        request, vocab, quality,
        flow=FLOW_STUDY,
        session_id=request.session.get(STUDY_SESSION_ID_KEY),
        touch_schedule=touch,
        extra={
            "in_queue": in_queue,
            "in_learning": in_learning,
            "touch": touch,
            "scope": request.session.get(STUDY_SCOPE_KEY) or "",
            "mode": request.session.get(STUDY_MODE_KEY) or SESSION_TYPE_FLASHCARD,
            "total": request.session.get(STUDY_TOTAL_KEY) or 0,
        },
    )

    # Bỏ đúng từ vừa ôn khỏi hàng đợi (không dựa vào vị trí đầu: người dùng
    # bấm nút hai lần / back rồi gửi lại vẫn không làm lệch hàng đợi).
    if in_queue:
        queue.remove(vocab.pk)
    if touch:
        if result is not None and result.in_session:
            if not in_learning:
                learning.append(vocab.pk)
        elif in_learning:
            learning.remove(vocab.pk)
    elif quality < 3:
        queue.append(vocab.pk)
    request.session[STUDY_QUEUE_KEY] = queue
    request.session[STUDY_LEARNING_KEY] = learning


def _restore_study_state(request, entry, session):
    """Hoàn tác trong phiên theo hàng đợi: đưa từ về đúng chỗ cũ.

    Nếu lần chấm đó làm phiên kết thúc (khoá session đã bị dọn), dựng lại
    phiên với đúng cờ "ôn thêm" cũ — không thì lượt chấm lại sẽ rơi về mặc
    định "đẩy lịch" và làm xô lịch của một lượt ôn thêm.
    """
    if STUDY_QUEUE_KEY not in request.session:
        request.session[STUDY_QUEUE_KEY] = []
        request.session[STUDY_LEARNING_KEY] = []
        request.session[STUDY_TOTAL_KEY] = entry.get("total") or 1
        request.session[STUDY_SCOPE_KEY] = entry.get("scope") or message("learning.study.scope.all")
        request.session[STUDY_TOUCH_SCHEDULE_KEY] = entry.get("touch", True)
        request.session[STUDY_MODE_KEY] = entry.get("mode") or SESSION_TYPE_FLASHCARD
    if session is not None:
        request.session[STUDY_SESSION_ID_KEY] = session.pk

    vocab_id = entry["vocab"]
    queue = list(request.session.get(STUDY_QUEUE_KEY) or [])
    learning = list(request.session.get(STUDY_LEARNING_KEY) or [])
    if entry.get("in_queue") and vocab_id not in queue:
        queue.insert(0, vocab_id)
    if entry.get("in_learning") and vocab_id not in learning:
        learning.append(vocab_id)
    elif not entry.get("in_learning") and vocab_id in learning:
        learning.remove(vocab_id)
    request.session[STUDY_QUEUE_KEY] = queue
    request.session[STUDY_LEARNING_KEY] = learning


def _next_queue_word(request):
    """Từ kế tiếp của phiên theo hàng đợi.

    Thứ tự: từ vừa hoàn tác -> từ đang học đã tới giờ -> đầu hàng đợi ->
    (hết hàng đợi) học trước từ đang học chưa tới giờ, sớm nhất trước.
    Trả về (word, remaining, ahead_minutes).
    """
    queue = list(request.session.get(STUDY_QUEUE_KEY) or [])
    learning = list(request.session.get(STUDY_LEARNING_KEY) or [])
    now = timezone.now()

    learning_rows = sorted(
        UserVocabularyProgress.objects.filter(
            user=request.user, vocabulary_id__in=learning,
            card_state__in=srs.IN_SESSION_STATES,
        ).values_list("vocabulary_id", "due_at"),
        key=lambda row: (row[1] or now, row[0]),
    )
    # Từ đã tốt nghiệp ở màn khác / đã bị xoá thì không còn "đang học" nữa.
    still_learning = [vid for vid, _ in learning_rows]
    if still_learning != learning:
        learning = [vid for vid in learning if vid in still_learning]
        request.session[STUDY_LEARNING_KEY] = learning
    remaining = len(set(queue) | set(learning))

    forced = _forced_word(request, FLOW_STUDY)
    if forced is not None:
        return forced, max(remaining, 1), 0

    due_ids = [vid for vid, due_at in learning_rows if (due_at or now) <= now]
    ahead_rows = [(vid, due_at) for vid, due_at in learning_rows if (due_at or now) > now]
    candidates = [(vid, 0) for vid in due_ids] + [(vid, 0) for vid in queue]
    candidates += [
        (vid, max(1, round((due_at - now).total_seconds() / 60))) for vid, due_at in ahead_rows
    ]
    for vocab_id, ahead in candidates:
        # Từ có thể đã bị xoá sau khi hàng đợi được chốt — bỏ qua, đừng 404
        # giữa lúc người ta đang học.
        word = Vocabulary.objects.filter(pk=vocab_id).first()
        if word is not None:
            return word, remaining, ahead
        if vocab_id in queue:
            queue.remove(vocab_id)
            request.session[STUDY_QUEUE_KEY] = queue
        remaining = max(0, remaining - 1)
    return None, 0, 0


def _study_done(request):
    session_id = request.session.get(STUDY_SESSION_ID_KEY)
    if not session_id:
        return 0
    return (
        StudySession.objects.filter(pk=session_id)
        .values_list("words_reviewed", flat=True)
        .first()
        or 0
    )


def _scope_label(topics):
    """Nhãn "đang học phạm vi nào" hiện trên thanh tiến độ."""
    if not topics:
        return message("learning.study.scope.all")
    if len(topics) == 1:
        return topics[0].display_name
    return message("learning.study.scope.many", count=len(topics))


@login_required
@require_POST
def study_start_view(request):
    """Nhận bộ lọc từ SC05, chốt hàng đợi rồi chuyển sang màn học."""
    topics = vocab_selectors.selected_topics(request.POST)
    query = (request.POST.get(vocab_selectors.SEARCH_PARAM) or "").strip()
    statuses = vocab_selectors.clean_statuses(
        request.POST.getlist(vocab_selectors.STATUS_PARAM)
    )
    limit = vocab_selectors.clean_session_limit(
        request.POST.get(vocab_selectors.LIMIT_PARAM)
    )

    words = vocab_selectors.filter_vocabulary(
        request.user, topics=topics, query=query, statuses=statuses
    )
    queue = services.build_study_queue(request.user, words, limit=limit)

    if not queue:
        flash.error(request, message("learning.study.error.empty_queue"))
        return redirect("vocabulary:index")

    # Phiên đang dở (nếu có) coi như kết thúc tại đây — người dùng vừa chủ
    # động chọn một tập từ khác.
    _clear_study_session(request)

    study_session = StudySession.objects.create(
        user=request.user,
        # Một chủ đề thì ghi nhận được vào lịch sử/streak theo chủ đề; nhiều
        # chủ đề thì để trống (StudySession.topic cho phép null).
        topic=topics[0] if len(topics) == 1 else None,
        session_type=SESSION_TYPE_FLASHCARD,
        started_at=timezone.now(),
    )
    request.session[STUDY_QUEUE_KEY] = queue
    request.session[STUDY_LEARNING_KEY] = []
    request.session[STUDY_TOTAL_KEY] = len(queue)
    request.session[STUDY_SESSION_ID_KEY] = study_session.pk
    request.session[STUDY_SCOPE_KEY] = _scope_label(topics)
    # Phiên bắt đầu từ SC05 luôn là ôn "chính thức": chấm điểm và đẩy lịch.
    request.session[STUDY_TOUCH_SCHEDULE_KEY] = True
    request.session[STUDY_MODE_KEY] = SESSION_TYPE_FLASHCARD
    return redirect("learning:study")


@login_required
def study_view(request):
    """Màn học một thẻ của phiên theo bộ lọc — dùng CHUNG template với SC04."""
    scope_label = request.session.get(STUDY_SCOPE_KEY) or message("learning.study.scope.all")
    word, remaining, ahead = _next_queue_word(request)

    if word is None:
        session = _clear_study_session(request)
        undo = _last_undo(request, FLOW_STUDY)
        return render(request, "learning/flashcard.html", {
            "word": None, "scope_label": scope_label, "is_study_session": True,
            "summary": _session_summary(session),
            "due_tomorrow": services.count_due_tomorrow(request.user),
            "undo_word": undo["word"] if undo else "",
        })

    touch = _touches_schedule(request)
    context = {
        "topic": None,
        "word": word,
        **_progress_numbers(_study_done(request), remaining),
        "ahead_minutes": ahead,
        "scope_label": scope_label,
        "review_action": reverse("learning:study_review", args=[word.pk]),
        "topic_slug_value": "",
        "is_study_session": True,
        "is_extra_review": not touch,
        "examples": word.examples.all()[:3],
        "comments": Contribution.objects.filter(
            target_vocabulary=word,
            contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            status_code=STATUS_APPROVED,
        ).order_by("-created_at"),
        **_card_context(request, word, flow=FLOW_STUDY, show_preview=touch),
    }
    return render(request, "learning/flashcard.html", context)


@login_required
@require_POST
def study_review_view(request, vocabulary_id):
    """4 nút Quên/Khó/Nhớ/Dễ của phiên học theo bộ lọc."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    quality = QUALITY_MAP.get(request.POST.get("quality"), 3)
    _grade_word(request, vocab, quality)
    return redirect("learning:study")


@login_required
@require_POST
def study_end_view(request):
    """Kết thúc phiên sớm — đóng StudySession và dọn hàng đợi."""
    _clear_study_session(request)
    return redirect("learning:dashboard")


# =============================================================================
# SC15 — Ôn tập
# -----------------------------------------------------------------------------
# Trang này KHÔNG dựng hàng đợi riêng: nó chọn tập từ bằng
# `selectors.studied_vocabulary()` rồi đi qua ĐÚNG luồng study_* đã có
# (`build_study_queue` -> session -> study_view/study_quiz_view). Khác biệt
# duy nhất là cờ STUDY_TOUCH_SCHEDULE_KEY: với các phạm vi "ôn thêm" (chưa đến
# hạn / đã thuộc) phiên chỉ ghi nhận đúng-sai, không đẩy lịch SM-2.
# =============================================================================

REVIEW_VIEW_PARAM = "view"
REVIEW_VIEW_TOPIC = "topic"
REVIEW_VIEW_MEMORY = "memory"
REVIEW_VIEW_CALENDAR = "calendar"
REVIEW_VIEWS = (REVIEW_VIEW_TOPIC, REVIEW_VIEW_MEMORY, REVIEW_VIEW_CALENDAR)

# Ba thẻ "ôn thêm" dưới khối đầu trang. `count_key` trỏ vào kết quả của
# `services.get_review_overview()` nên số trên thẻ và số từ thật sự ôn được
# luôn đến từ cùng một truy vấn.
REVIEW_DECKS = (
    {"scope": vocab_selectors.SCOPE_LEECH, "count_key": "leech", "emoji": "🔁"},
    {"scope": vocab_selectors.SCOPE_UPCOMING, "count_key": "upcoming", "emoji": "🗓"},
    {"scope": vocab_selectors.SCOPE_MASTERED, "count_key": "mastered", "emoji": "⭐"},
)


def _clean_review_view(raw):
    return raw if raw in REVIEW_VIEWS else REVIEW_VIEW_TOPIC


def _review_scope_label(scope, topics):
    """Nhãn phạm vi hiện trên thanh tiến độ của phiên ôn."""
    scope_label = label(f"learning.review.scope.{scope}")
    if not topics:
        return scope_label
    return message(
        "learning.review.scope_with_topics",
        scope=scope_label,
        topics=_scope_label(topics),
    )


@login_required
def review_view(request):
    """SC15_OnTap — thống kê từ đã học + các lối vào một lượt ôn.

    Ba bảng thống kê là BA GÓC NHÌN của cùng một khu vực, chuyển bằng
    `?view=` chứ không phải JavaScript — tắt JS vẫn đổi tab được, và mỗi tab
    bookmark/chia sẻ được như mọi trang khác của repo.
    """
    user = request.user
    active_view = _clean_review_view(request.GET.get(REVIEW_VIEW_PARAM))
    overview = services.get_review_overview(user)

    decks = [
        {
            "scope": deck["scope"],
            "emoji": deck["emoji"],
            "count": overview[deck["count_key"]],
            "label_key": f"learning.review.scope.{deck['scope']}",
            "hint_key": f"learning.review.hint.{deck['scope']}",
            "is_extra": not vocab_selectors.touches_schedule(deck["scope"]),
        }
        for deck in REVIEW_DECKS
    ]

    context = {
        "active_nav": "review",
        "overview": overview,
        "decks": decks,
        "active_view": active_view,
        "views": REVIEW_VIEWS,
        "topics": Topic.objects.all().order_by("name"),
        "limit_choices": vocab_selectors.SESSION_LIMIT_CHOICES,
        "session_limit": vocab_selectors.DEFAULT_SESSION_LIMIT,
        # Thẻ "Ôn thêm" và nút "Ôn →" theo chủ đề KHÔNG có ô chọn số từ, còn nút
        # thì ghi rõ con số ("Ôn 101 từ") -> phải ôn ĐỦ nhóm đó, không được cắt
        # theo DEFAULT_SESSION_LIMIT (bug 27/09/2026: bấm "Ôn 101 từ" chỉ ra 20 thẻ).
        # Chỉ khối "Đến hạn hôm nay" có <select> mới dùng session_limit.
        "full_limit": vocab_selectors.SESSION_LIMIT_ALL,
        "wordlists": UserWordlist.objects.filter(user=user).order_by("-updated_at"),
        # Chỉ truy vấn đúng bảng của tab đang mở — ba tab là ba truy vấn khác
        # nhau, không việc gì chạy cả ba mỗi lần tải trang.
        "topic_rows": services.get_topic_review_rows(user) if active_view == REVIEW_VIEW_TOPIC else [],
        "memory_rows": services.get_memory_distribution(user) if active_view == REVIEW_VIEW_MEMORY else [],
        "calendar": services.get_review_calendar(user) if active_view == REVIEW_VIEW_CALENDAR else [],
    }
    return render(request, "learning/review.html", context)


@login_required
@require_POST
def review_start_view(request):
    """Chốt hàng đợi cho một lượt ôn của SC15 rồi chuyển sang màn học."""
    scope = vocab_selectors.clean_review_scope(
        request.POST.get(vocab_selectors.REVIEW_SCOPE_PARAM)
    )
    topics = vocab_selectors.selected_topics(request.POST)
    limit = vocab_selectors.clean_session_limit(
        request.POST.get(vocab_selectors.LIMIT_PARAM)
    )
    mode = (
        SESSION_TYPE_QUIZ
        if request.POST.get("mode") == SESSION_TYPE_QUIZ
        else SESSION_TYPE_FLASHCARD
    )

    words = vocab_selectors.studied_vocabulary(request.user, topics=topics, scope=scope)
    queue = services.build_study_queue(request.user, words, limit=limit)
    if not queue:
        flash.error(request, message("learning.review.error.empty_queue"))
        return redirect("learning:review")

    _clear_study_session(request)
    study_session = StudySession.objects.create(
        user=request.user,
        topic=topics[0] if len(topics) == 1 else None,
        session_type=mode,
        started_at=timezone.now(),
    )
    request.session[STUDY_QUEUE_KEY] = queue
    request.session[STUDY_TOTAL_KEY] = len(queue)
    request.session[STUDY_SESSION_ID_KEY] = study_session.pk
    request.session[STUDY_SCOPE_KEY] = _review_scope_label(scope, topics)
    request.session[STUDY_TOUCH_SCHEDULE_KEY] = vocab_selectors.touches_schedule(scope)
    request.session[STUDY_MODE_KEY] = mode

    if mode == SESSION_TYPE_QUIZ:
        return redirect("learning:study_quiz")
    return redirect("learning:study")


@login_required
def study_quiz_view(request):
    """Trắc nghiệm trên hàng đợi đã chốt — bản "nhiều chủ đề" của SC06.

    `quiz_view` (SC06) chỉ chạy được trong PHẠM VI MỘT CHỦ ĐỀ vì route của nó
    mang slug. Màn này dùng lại y nguyên template và `get_quiz_choices()`,
    chỉ khác nguồn hàng đợi (session thay vì `get_topic_queue`).
    """
    scope_label = request.session.get(STUDY_SCOPE_KEY) or message("learning.study.scope.all")
    word, remaining, _ahead = _next_queue_word(request)

    if word is None:
        session = _clear_study_session(request)
        if session and session.words_reviewed:
            flash.success(request, message(
                "learning.quiz.success.session_complete",
                correct=session.correct_answers, total=session.words_reviewed,
            ))
        return render(request, "learning/quiz.html", {
            "word": None, "scope_label": scope_label,
        })

    # Nhiễu lấy theo chủ đề ĐẦU TIÊN của từ (hàng đợi có thể gộp nhiều chủ
    # đề); từ không có chủ đề nào thì get_quiz_choices tự lấy từ toàn bộ từ điển.
    topic = word.topics.first()
    context = {
        "topic": topic,
        "word": word,
        **_progress_numbers(_study_done(request), remaining),
        "choices": services.get_quiz_choices(word, topic),
        "scope_label": scope_label,
        "answer_action": reverse("learning:study_quiz_answer", args=[word.pk]),
        "is_extra_review": not _touches_schedule(request),
    }
    return render(request, "learning/quiz.html", context)


@login_required
@require_POST
def study_quiz_answer_view(request, vocabulary_id):
    """Nộp một câu của phiên trắc nghiệm theo hàng đợi."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    is_correct = request.POST.get("choice") == str(vocab.pk)
    # Quy đổi giống SC06: đúng -> 4 ("Nhớ"), sai -> 0 ("Quên rồi").
    _grade_word(request, vocab, 4 if is_correct else 0)

    if is_correct:
        flash.success(request, message("learning.quiz.feedback.correct"))
    else:
        flash.error(request, message("learning.quiz.feedback.wrong", meaning=vocab.meaning_vi))
    return redirect("learning:study_quiz")
