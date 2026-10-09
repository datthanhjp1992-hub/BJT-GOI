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
import json

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_POST

from apps.core import pagination
from apps.core.constants import SESSION_TYPE_FLASHCARD, SESSION_TYPE_QUIZ
from apps.core.properties import label, message
from apps.gamification import services as gamification_services
from apps.gamification.services import CONTRIBUTION_TYPE_COMMENT
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
        # spec.md T3.1: một nút chính "Học hôm nay" thay cho "Học tiếp chủ đề X".
        "daily": services.get_daily_overview(user),
        # spec.md T3.2: chưa học gì (không tiến độ, không phiên) -> mời mở lại
        # màn hướng dẫn lần đầu. stats đã đếm tiến độ, không tốn thêm query đó.
        "show_onboarding": not stats["words_started"]
        and not StudySession.objects.filter(user=user).exists(),
        "suggested_topics": services.get_suggested_topics(user),
        "active_nav": "home",
    }
    return render(request, "learning/dashboard.html", context)


# =============================================================================
# Render màn học dạng FRAGMENT (spec.md T1.2 — chấm thẻ không tải lại trang)
# -----------------------------------------------------------------------------
# static/js/main.js gửi các form của màn học bằng fetch() kèm header
# X-Card-Partial: 1. View POST (chấm điểm, hoàn tác...) KHÔNG đổi gì — vẫn
# redirect như cũ; fetch() tự đi theo redirect cùng origin và giữ header tự
# đặt, nên GET sau redirect nhận được header và chỉ trả phần thẻ
# (learning/_card_panel.html), không kèm sidebar/CSS/JS. Response fragment mang
# header X-Card-Partial: 1 để JS phân biệt với trang đầy đủ (vd hoàn tác hết
# lượt bị đẩy về dashboard) — trang đầy đủ thì JS chuyển hẳn sang URL đó.
# Tắt JavaScript: không có header -> trang đầy đủ, chạy y như trước.
# =============================================================================

PARTIAL_HEADER = "X-Card-Partial"
CARD_TEMPLATE = "learning/flashcard.html"
CARD_PANEL_TEMPLATE = "learning/_card_panel.html"


def _wants_partial(request):
    return request.headers.get(PARTIAL_HEADER) == "1"


def _render_card(request, context):
    """Render màn học: trang đầy đủ, hoặc chỉ phần thẻ khi JS yêu cầu."""
    partial = _wants_partial(request)
    context = {
        **context,
        "is_partial": partial,
        "show_reading_on_front": getattr(request.user, "show_reading_on_front", True),
    }
    response = render(request, CARD_PANEL_TEMPLATE if partial else CARD_TEMPLATE, context)
    if partial:
        response[PARTIAL_HEADER] = "1"
    # Cùng URL nhưng hai dạng nội dung — trình duyệt/proxy không được cache lẫn.
    patch_vary_headers(response, [PARTIAL_HEADER])
    return response


def _flashcard_session_keys(topic_slug):
    """Hai khoá trong request.session để nhớ TỔNG số thẻ và bản ghi
    StudySession của phiên flashcard đang chạy cho 1 chủ đề. Khoá theo
    topic_slug nên user học nhiều chủ đề (tab khác nhau) không đụng nhau.

    Khoá "total" giữ {"session": <StudySession.pk>, "ids": [...]} — tập id
    mọi từ đã xuất hiện trong phiên, để mẫu số "Thẻ x/N" đếm theo TỪ và không
    tăng mỗi khi một từ quay lại ở bước học (xem `_topic_progress`)."""
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


# Lần chấm ĐẦU TIÊN của từng từ trong một StudySession:
#   {"<session pk>": {"<vocab id>": quality}}
# StudySession chỉ đếm LƯỢT chấm (words_reviewed) — một từ quay lại 3 lần là
# 3 lượt — nên không trả lời được "lượt này học bao nhiêu TỪ, nhớ ngay bao
# nhiêu từ". Dict này bù đúng chỗ đó cho màn tổng kết và thanh "đã xem".
# Giữ FIRST_GRADES_MAX phiên gần nhất: hoàn tác ngay sau khi hết lượt vẫn
# phải tìm thấy dữ liệu của phiên vừa đóng.
FIRST_GRADES_KEY = "learning_first_grades"
FIRST_GRADES_MAX = 5


def _first_grades(request, session_id):
    """{vocab_id: quality lần chấm đầu} của một phiên (dict rỗng nếu chưa có)."""
    if not session_id:
        return {}
    data = request.session.get(FIRST_GRADES_KEY) or {}
    return {int(k): v for k, v in (data.get(str(session_id)) or {}).items()}


def _record_first_grade(request, session_id, vocab_id, quality):
    """Ghi lần chấm đầu của từ trong phiên. True nếu đây đúng là lần đầu."""
    if not session_id:
        return False
    data = dict(request.session.get(FIRST_GRADES_KEY) or {})
    grades = dict(data.get(str(session_id)) or {})
    if str(vocab_id) in grades:
        return False
    grades[str(vocab_id)] = quality
    data[str(session_id)] = grades
    for old in sorted(data, key=int)[:-FIRST_GRADES_MAX]:
        data.pop(old, None)
    request.session[FIRST_GRADES_KEY] = data
    return True


def _forget_first_grade(request, session_id, vocab_id):
    """Hoàn tác đúng lần chấm đầu -> từ coi như chưa gặp trong phiên."""
    data = dict(request.session.get(FIRST_GRADES_KEY) or {})
    grades = dict(data.get(str(session_id)) or {})
    if grades.pop(str(vocab_id), None) is not None:
        data[str(session_id)] = grades
        request.session[FIRST_GRADES_KEY] = data


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
    first = _record_first_grade(request, session_id, vocab.pk, quality)

    entry = {
        "vocab": vocab.pk,
        "word": vocab.word,
        "snap": snapshot,
        "sid": session_id,
        "correct": correct,
        "first": first,
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


# Bốn nút chấm: (mã POST, key nhãn, class màu, là nút chính). Màu nằm ở CSS
# (base.css .btn-grade.is-* + token --grade-* của theme) — spec.md T2.2.
GRADE_BUTTONS = (
    ("quen", "learning.flashcard.button.forgot", "is-forgot", False),
    ("kho", "learning.flashcard.button.hard", "is-hard", False),
    ("nho", "learning.flashcard.button.good", "is-good", False),
    ("de", "learning.flashcard.button.easy", "", True),
)


def _card_context(request, word, *, flow, show_preview=True, session_id=None):
    """Phần context mô tả THẺ đang hiện: giai đoạn, 4 nút kèm khoảng cách, hoàn tác."""
    progress = UserVocabularyProgress.objects.filter(user=request.user, vocabulary=word).first()
    state = progress.card_state if progress else srs.NEW
    # Khoảng cách ôn lại dưới nút là tuỳ chọn ở SC08 (mặc định ẩn) — với
    # "hết lượt rồi mới ôn lại", "1 phút / 6 phút" không còn khớp lúc từ quay lại.
    show_preview = show_preview and getattr(request.user, "show_review_interval", False)
    previews = services.grade_previews(progress) if show_preview else {}
    buttons = [
        {
            "code": code,
            # Phím tắt 1-4 (static/js/main.js) — theo đúng thứ tự hiển thị.
            "key": index,
            "label_key": label_key,
            "css": css,
            "primary": primary,
            "delay": _delay_text(previews[QUALITY_MAP[code]]) if previews else "",
        }
        for index, (code, label_key, css, primary) in enumerate(GRADE_BUTTONS, start=1)
    ]
    undo = _last_undo(request, flow)
    return {
        "card_state": state,
        "card_state_key": f"learning.flashcard.state.{state}",
        # Từ đã gặp trong phiên này và đang quay lại -> nhãn "Gặp lại".
        "is_repeat": word.pk in _first_grades(request, session_id),
        "grade_buttons": buttons,
        "undo_word": undo["word"] if undo else "",
    }


# Tối đa bao nhiêu từ "cần ôn thêm" được liệt kê/gửi sang lượt ôn thêm.
RETRY_MAX = 200


def _session_summary(request, session):
    """Tổng kết một phiên đã đóng — hiện trên màn "đã ôn xong".

    Đếm theo TỪ chứ không theo lượt chấm (từ 01/10/2026): bộ 50 từ mà có 15
    lần gặp lại vẫn là "50 từ", số lượt chấm (65) chỉ ghi phụ bên dưới.
    "Nhớ ngay" = lần chấm ĐẦU TIÊN của từ là Khó/Nhớ/Dễ (quality >= 3, cùng
    ngưỡng với StudySession.correct_answers); bấm Quên lần đầu thì từ vào
    danh sách "cần ôn thêm".
    """
    if session is None or not session.words_reviewed:
        return None
    grades = _first_grades(request, session.pk)
    if not grades:
        # Phiên mở trước khi có FIRST_GRADES_KEY — chỉ còn số lượt chấm.
        return {"reviewed": session.words_reviewed, "words": 0}
    again_ids = [vid for vid, q in grades.items() if q < 3]
    remembered = len(grades) - len(again_ids)
    by_id = Vocabulary.objects.in_bulk(again_ids[:RETRY_MAX])
    return {
        "minutes": _session_minutes(session),
        "reviewed": session.words_reviewed,
        "words": len(grades),
        "remembered": remembered,
        "percent": round(remembered * 100 / len(grades)),
        "again": len(again_ids),
        "again_words": [by_id[vid] for vid in again_ids if vid in by_id],
    }


def _session_minutes(session):
    """Thời gian học của phiên, làm tròn LÊN theo phút (học 20 giây vẫn là
    "1 phút", không phải 0). Phiên chưa đóng thì tính tới bây giờ."""
    end = session.ended_at or timezone.now()
    seconds = max(0, (end - session.started_at).total_seconds())
    return max(1, -(-int(seconds) // 60))


def _progress_numbers(total, remaining, seen=0):
    """Tiến độ đếm theo TỪ, không theo lượt chấm — hai lớp:

    * `seen` / `seen_percent`: số từ ĐÃ GẶP ít nhất một lần trong phiên
      (lớp nhạt của thanh tiến độ). Tăng đều sau mỗi từ mới, nên người học
      thấy mình đang đi tới dù vừa có từ quay lại.
    * `done` / `percent`: số từ ĐÃ THUỘC — rời phiên (tốt nghiệp). Từ bấm
      Quên/Khó/Nhớ còn ở bước học vẫn nằm trong `remaining`.

    `position` giữ cho màn trắc nghiệm ("Câu hỏi x/N").
    """
    total = max(total or 0, remaining, 1)
    done = total - remaining
    seen = min(max(seen or 0, done), total)
    return {
        "position": min(done + 1, total),
        "total": total,
        "done": done,
        "percent": round(done * 100 / total),
        "seen": seen,
        "seen_percent": round(seen * 100 / total),
    }


def _topic_progress(request, key, session, words):
    """Tiến độ cho phiên theo 1 chủ đề (SC04/SC06) — hàng đợi ở đây tính lại
    mỗi lần nên không có tổng chốt sẵn; ta nhớ tập id mọi từ đã xuất hiện
    trong phiên (theo StudySession) và lấy đó làm mẫu số."""
    data = request.session.get(key)
    if not isinstance(data, dict) or data.get("session") != session.pk:
        data = {"session": session.pk, "ids": []}
    current = {w.pk for w in words}
    seen = set(data.get("ids") or []) | current
    request.session[key] = {"session": session.pk, "ids": sorted(seen)}
    return _progress_numbers(
        len(seen), len(current), seen=len(_first_grades(request, session.pk))
    )


@login_required
def flashcard_view(request, topic_slug):
    """SC04_HocTuVung — 1 thẻ mỗi lần, theo flow ôn tập của
    `services.get_topic_queue`: từ đang học tới giờ -> từ đến hạn -> từ mới
    (tối đa `daily_review_goal`/ngày) -> học trước từ đang học chưa tới giờ."""
    topic = get_object_or_404(Topic, slug=topic_slug)
    total_key, session_id_key = _flashcard_session_keys(topic.slug)
    flow = _topic_flow(topic.slug)
    queue = services.get_topic_queue(
        request.user, topic, unlocked_ids=_unlocked_new_ids(request, topic.slug)
    )
    forced = _forced_word(request, flow)
    word = forced or (queue.words[0] if queue.words else None)

    if word is None:
        # Hết thẻ cần ôn (hoặc chủ đề chưa có từ nào) — đóng phiên đang mở và
        # dọn khoá session để lần mở lại sau tính là một lượt ôn mới.
        session = _close_study_session(request, session_id_key)
        request.session.pop(total_key, None)
        undo = _last_undo(request, flow)
        more_new_batch = min(queue.more_new_count, queue.new_limit or 1)
        return _render_card(request, {
            "topic": topic, "word": None, "scope_label": topic.display_name,
            "summary": _session_summary(request, session),
            "streak_days": services.get_streak_days(request.user),
            "queue": queue,
            "more_new_batch": more_new_batch,
            # Khối "Vẫn học thêm" báo trước cái giá: ngày mai thêm ~N từ ôn.
            "over_limit": (
                services.over_limit_forecast(request.user, more_new_batch)
                if queue.more_new else None
            ),
            "due_tomorrow": services.count_due_tomorrow(request.user),
            "undo_word": undo["word"] if undo else "",
        })

    session = _ensure_open_session(request, session_id_key, topic, SESSION_TYPE_FLASHCARD)
    words = list(queue.words) + ([forced] if forced and forced not in queue.words else [])

    context = {
        "topic": topic,
        "word": word,
        **_topic_progress(request, total_key, session, words),
        "queue": queue,
        "ahead_minutes": 0 if forced else queue.ahead_minutes,
        # Ba khoá dưới đây để flashcard.html dùng được cho CẢ HAI lối vào:
        # học theo 1 chủ đề (màn này) và học theo bộ lọc của SC05 (study_view).
        "scope_label": topic.display_name,
        "review_action": reverse("learning:flashcard_review", args=[word.pk]),
        "topic_slug_value": topic.slug,
        "examples": word.examples.all()[:3],
        "comments": gamification_services.get_vocabulary_comments(word),
        **_card_context(request, word, flow=flow, session_id=session.pk),
    }
    return _render_card(request, context)


@login_required
@require_POST
def flashcard_end_view(request, topic_slug):
    """"Kết thúc phiên" của SC04 (spec.md T6.2): từ đã chấm trong phiên mà còn
    ở bước học được hẹn sang mai, rồi đóng StudySession.

    SC04 không giữ danh sách từ đang học trong session như phiên study_*, nên
    lấy tập từ đã chấm của phiên (`_first_grades`) — postpone_learning() tự bỏ
    qua từ đã tốt nghiệp.
    """
    total_key, session_id_key = _flashcard_session_keys(topic_slug)
    session_id = request.session.get(session_id_key)
    postponed = services.postpone_learning(request.user, list(_first_grades(request, session_id)))
    _close_study_session(request, session_id_key)
    request.session.pop(total_key, None)
    _flash_postponed(request, postponed)
    return redirect("learning:dashboard")


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
    undone = _apply_undo(request)
    if undone is None:
        flash.info(request, message("learning.flashcard.error.nothing_to_undo"))
        return redirect("learning:dashboard")

    entry, session = undone
    flow = entry.get("flow", "")
    flash.info(request, message("learning.flashcard.success.undone", word=entry.get("word", "")))

    if flow == FLOW_STUDY:
        return redirect("learning:study")
    topic_slug = entry.get("topic", "")
    if topic_slug and Topic.objects.filter(slug=topic_slug).exists():
        if session is not None:
            _, session_id_key = _flashcard_session_keys(topic_slug)
            request.session[session_id_key] = session.pk
        return redirect("learning:flashcard", topic_slug=topic_slug)
    request.session.pop(FORCE_KEY, None)
    return redirect("learning:dashboard")


def _apply_undo(request):
    """Trả lần chấm trên cùng của ngăn hoàn tác (của hôm nay) về như cũ.

    Dùng chung cho nút "Hoàn tác" (`undo_view`) và lệnh "undo" của
    `study_sync_view`. Trả (entry, StudySession | None), hoặc None nếu không
    còn gì để hoàn tác.
    """
    stack = list(request.session.get(UNDO_KEY) or [])
    today = request.user.local_today().isoformat()
    if not stack or stack[-1].get("day") != today:
        return None

    entry = stack.pop()
    request.session[UNDO_KEY] = stack
    vocab_id = entry["vocab"]

    progress = UserVocabularyProgress.objects.filter(
        user=request.user, vocabulary_id=vocab_id
    ).first()
    if entry["snap"] is None:
        if progress is not None:
            progress.delete()
            services.invalidate_due_badge(request.user.pk)
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
    if entry.get("first") and entry.get("sid"):
        _forget_first_grade(request, entry["sid"], vocab_id)

    flow = entry.get("flow", "")
    request.session[FORCE_KEY] = {"vocab": vocab_id, "flow": flow}
    if flow == FLOW_STUDY:
        _restore_study_state(request, entry, session)
    return entry, session


DISCUSSION_ANCHOR = "study-discussion"


@login_required
@require_POST
def flashcard_comment(request, vocabulary_id):
    """Gửi bình luận cho 1 từ ngay trên màn flashcard — tạo Contribution loại
    'Bình luận'. Từ 27/09/2026 bình luận ĐĂNG THẲNG (không qua admin duyệt),
    hiện ngay dưới thẻ; người viết/admin xoá được sau."""
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
    # Neo #study-discussion: main.js lật thẻ + mở sẵn khu thảo luận để người
    # gửi thấy ngay bình luận của mình (khu này mặc định gập, xem T1.5).
    if not topic_slug:
        target = reverse("learning:study")
    else:
        target = reverse("learning:flashcard", kwargs={"topic_slug": topic_slug})
    return redirect(f"{target}#{DISCUSSION_ANCHOR}")


def _extra_new_key(topic_slug):
    return f"flashcard_extra_new_{topic_slug}"


def _unlocked_new_ids(request, topic_slug):
    """Từ mới đã mở thêm HÔM NAY cho chủ đề này (nút "Học thêm N từ mới").
    Sang ngày khác thì bỏ — hạn mức ngày mới tự cho từ mới trở lại."""
    data = request.session.get(_extra_new_key(topic_slug))
    if not isinstance(data, dict) or data.get("date") != request.user.local_today().isoformat():
        return []
    return data.get("ids") or []


@login_required
@require_POST
def flashcard_more_new_view(request, topic_slug):
    """Mở thêm một nhóm từ mới cho chủ đề khi đã chạm hạn mức ngày — không
    phải vào Cài đặt đổi "Số từ mới mỗi ngày" chỉ để học nốt vài từ."""
    topic = get_object_or_404(Topic, slug=topic_slug)
    ids = services.pick_extra_new_words(request.user, topic)
    if ids:
        merged = list(dict.fromkeys(_unlocked_new_ids(request, topic.slug) + ids))
        request.session[_extra_new_key(topic.slug)] = {
            "date": request.user.local_today().isoformat(),
            "ids": merged,
        }
    return redirect("learning:flashcard", topic.slug)


def _quiz_session_keys(topic_slug):
    """Giống `_flashcard_session_keys` nhưng khoá riêng namespace "quiz_" —
    user có thể mở song song flashcard và quiz của CÙNG một chủ đề (hai tab)
    mà không đụng phiên của nhau."""
    return f"quiz_total_{topic_slug}", f"quiz_session_id_{topic_slug}"


def _flash_quiz_score(request, session):
    """Điểm cuối lượt trắc nghiệm, đếm theo TỪ: "đúng ngay lần đầu / số từ"."""
    summary = _session_summary(request, session)
    if not summary:
        return
    if summary["words"]:
        correct, total = summary["remembered"], summary["words"]
    else:
        correct, total = session.correct_answers, session.words_reviewed
    flash.success(request, message(
        "learning.quiz.success.session_complete", correct=correct, total=total,
    ))


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
        _flash_quiz_score(request, session)
        return render(request, "learning/quiz.html", {
            "topic": topic, "word": None, "scope_label": topic.display_name,
        })

    session = _ensure_open_session(request, session_id_key, topic, SESSION_TYPE_QUIZ)
    word = queue.words[0]

    context = {
        "topic": topic,
        "word": word,
        **_topic_progress(request, total_key, session, queue.words),
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
# {"sid": StudySession.pk, "seq": n} — số thứ tự lệnh cuối cùng study_sync_view
# đã xử lý cho phiên đó. Lệnh gửi lại (mạng chập chờn, sendBeacon lúc đóng tab)
# có seq <= n thì bỏ qua, không chấm hai lần (spec.md T4.3).
STUDY_SEQ_KEY = "study_seq"


def _postpone_study_learning(request):
    """Từ còn ở bước học của phiên theo hàng đợi -> hẹn sang mai (spec.md T6.2).

    Chỉ phiên chính thức: phiên "ôn thêm" không đụng lịch. Trả về số từ đã hoãn.
    """
    ids = request.session.pop(STUDY_LEARNING_KEY, None) or []
    if not ids or not _touches_schedule(request):
        return 0
    return services.postpone_learning(request.user, ids)


def _clear_study_session(request):
    _postpone_study_learning(request)
    request.session.pop(STUDY_QUEUE_KEY, None)
    request.session.pop(STUDY_TOTAL_KEY, None)
    request.session.pop(STUDY_SCOPE_KEY, None)
    request.session.pop(STUDY_TOUCH_SCHEDULE_KEY, None)
    request.session.pop(STUDY_MODE_KEY, None)
    request.session.pop(STUDY_LEARNING_KEY, None)
    request.session.pop(STUDY_SEQ_KEY, None)
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

    Thứ tự: từ vừa hoàn tác -> đầu hàng đợi -> (hết hàng đợi) từ đang học,
    tới giờ sớm nhất trước; chưa tới giờ thì "học trước".

    Hàng đợi luôn đứng trước từ đang học ("hết lượt rồi mới ôn lại", từ
    01/10/2026): người học đi trọn các từ đã chọn rồi mới gặp lại từ bấm
    Quên/Khó/Nhớ, thay vì bị chen ngang sau mỗi 1-10 phút.
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
    candidates = [(vid, 0) for vid in queue] + [(vid, 0) for vid in due_ids]
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


def _study_progress(request, remaining):
    return _progress_numbers(
        request.session.get(STUDY_TOTAL_KEY), remaining,
        seen=len(_first_grades(request, request.session.get(STUDY_SESSION_ID_KEY))),
    )


def _scope_label(topics):
    """Nhãn "đang học phạm vi nào" hiện trên thanh tiến độ."""
    if not topics:
        return message("learning.study.scope.all")
    if len(topics) == 1:
        return topics[0].display_name
    return message("learning.study.scope.many", count=len(topics))


def _start_study_session(request, queue, scope_label, topic=None, touch=True,
                         mode=SESSION_TYPE_FLASHCARD):
    """Chốt `queue` (list id) thành một phiên study_* mới.

    Dùng chung cho mọi lối vào phiên theo hàng đợi: SC05 (`study_start_view`),
    SC15 (`review_start_view`), "Ôn thêm" ở màn tổng kết (`study_retry_view`)
    và "Học hôm nay" ở SC03 (`daily_start_view`). Phiên đang dở (nếu có) coi
    như kết thúc tại đây — người dùng vừa chủ động chọn một tập từ khác.
    `touch=False`: phiên "ôn thêm", chỉ ghi đúng/sai, không đẩy lịch SM-2.
    """
    _clear_study_session(request)
    study_session = StudySession.objects.create(
        user=request.user,
        # Một chủ đề thì ghi nhận được vào lịch sử/streak theo chủ đề; nhiều
        # chủ đề thì để trống (StudySession.topic cho phép null).
        topic=topic,
        session_type=mode,
        started_at=timezone.now(),
    )
    request.session[STUDY_QUEUE_KEY] = queue
    request.session[STUDY_LEARNING_KEY] = []
    request.session[STUDY_TOTAL_KEY] = len(queue)
    request.session[STUDY_SESSION_ID_KEY] = study_session.pk
    request.session[STUDY_SCOPE_KEY] = scope_label
    request.session[STUDY_TOUCH_SCHEDULE_KEY] = touch
    request.session[STUDY_MODE_KEY] = mode
    return study_session


@login_required
@require_POST
def daily_start_view(request):
    """Nút "Học hôm nay" ở SC03 — hàng đợi gom mọi chủ đề (spec.md T3.1)."""
    queue = services.build_daily_queue(request.user)
    if not queue:
        flash.info(request, message("learning.daily.hint.nothing_left"))
        return redirect("learning:dashboard")
    _start_study_session(request, queue, message("learning.daily.scope"))
    return redirect("learning:study")


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
        request.POST.get(vocab_selectors.LIMIT_PARAM),
        default=vocab_selectors.LIBRARY_DEFAULT_SESSION_LIMIT,
    )

    words = vocab_selectors.filter_vocabulary(
        request.user, topics=topics, query=query, statuses=statuses
    )
    # Hạn mức từ mới chung (spec.md T6.1). "Vẫn học thêm" mở thêm đúng MỘT
    # hạn mức mỗi lần bấm, không mở "tất cả".
    allowance = services.new_word_allowance(request.user)
    over_limit = request.POST.get(vocab_selectors.OVER_LIMIT_PARAM) == "1"
    plan = services.plan_study_queue(
        request.user, words, limit=limit,
        new_limit=allowance.left + (allowance.goal if over_limit else 0),
    )
    queue = plan.queue

    if not queue:
        if plan.held_new:
            # Toàn từ mới mà hôm nay đã hết hạn mức: quay lại đúng bộ lọc, SC05
            # hiện khối "Vẫn học thêm" để người học tự quyết.
            flash.warning(request, message(
                "learning.study.error.new_limit_reached",
                learned=allowance.learned_today, goal=allowance.goal,
            ))
            params = vocab_selectors.filter_params(
                [t.slug for t in topics], statuses, query, limit
            )
            return redirect(f"{reverse('vocabulary:index')}?{params.urlencode()}")
        flash.error(request, message("learning.study.error.empty_queue"))
        return redirect("vocabulary:index")
    if plan.held_new:
        flash.info(request, message(
            "learning.study.hint.new_held",
            learned=allowance.learned_today, goal=allowance.goal, held=plan.held_new,
        ))

    # Phiên bắt đầu từ SC05 luôn là ôn "chính thức": chấm điểm và đẩy lịch.
    _start_study_session(
        request, queue, _scope_label(topics),
        topic=topics[0] if len(topics) == 1 else None,
    )
    return redirect("learning:study")


@login_required
def study_view(request):
    """Màn học một thẻ của phiên theo bộ lọc — dùng CHUNG template với SC04."""
    scope_label = request.session.get(STUDY_SCOPE_KEY) or message("learning.study.scope.all")
    word, remaining, ahead = _next_queue_word(request)

    if word is None:
        session = _clear_study_session(request)
        undo = _last_undo(request, FLOW_STUDY)
        return _render_card(request, {
            "word": None, "scope_label": scope_label, "is_study_session": True,
            "summary": _session_summary(request, session),
            "streak_days": services.get_streak_days(request.user),
            "due_tomorrow": services.count_due_tomorrow(request.user),
            "undo_word": undo["word"] if undo else "",
        })

    touch = _touches_schedule(request)
    context = {
        "topic": None,
        "word": word,
        **_study_progress(request, remaining),
        "ahead_minutes": ahead,
        "scope_label": scope_label,
        "review_action": reverse("learning:study_review", args=[word.pk]),
        "topic_slug_value": "",
        "is_study_session": True,
        "is_extra_review": not touch,
        "examples": word.examples.all()[:3],
        "comments": gamification_services.get_vocabulary_comments(word),
        **_card_context(
            request, word, flow=FLOW_STUDY, show_preview=touch,
            session_id=request.session.get(STUDY_SESSION_ID_KEY),
        ),
    }
    context["deck"] = _study_deck(request, word, scope_label)
    return _render_card(request, context)


@login_required
@require_POST
def study_review_view(request, vocabulary_id):
    """4 nút Quên/Khó/Nhớ/Dễ của phiên học theo bộ lọc."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    quality = QUALITY_MAP.get(request.POST.get("quality"), 3)
    _grade_word(request, vocab, quality)
    return redirect("learning:study")


# =============================================================================
# Học liền mạch (spec.md T4.3, 06/10/2026)
# -----------------------------------------------------------------------------
# Trước đây mỗi lần chấm = POST study/review/<id>/ -> 302 -> GET study/, người
# học chờ ~2,5 s (đo thật trên Render) mới thấy thẻ kế. Giờ study_view nhúng
# sẵn BỘ THẺ (#study-deck, `_study_deck`) vào trang; static/js/study_deck.js
# tự chọn thẻ kế theo đúng luật của `_next_queue_word`, hiện ngay, rồi gửi
# ngầm các lệnh chấm/hoàn tác theo lô tới `study_sync_view`.
#
# Server vẫn là nơi giữ dữ liệu: lệnh "grade" gọi đúng `_grade_word`, lệnh
# "undo" gọi đúng `_apply_undo` — không có logic chấm thứ hai. JS gửi LẦN
# LƯỢT (một request mỗi lúc) vì session lưu trong DB: hai request ghi session
# cùng lúc sẽ đè mất hàng đợi của nhau. Tắt JS: form cũ chạy y như trước.
# =============================================================================

# Số thẻ nhúng sẵn trong trang / tải thêm mỗi lần (study_cards_view).
DECK_BATCH = 50
# Chặn trên số lệnh trong một lô gửi lên study_sync_view.
SYNC_OPS_MAX = 200


def _card_previews(request, progress):
    """Khoảng cách ôn lại dưới 4 nút cho MỘT thẻ — cùng điều kiện hiện với
    `_card_context` (tuỳ chọn SC08 + không phải lượt "ôn thêm"). None = ẩn."""
    if not (getattr(request.user, "show_review_interval", False) and _touches_schedule(request)):
        return None
    previews = services.grade_previews(progress)
    return {code: _delay_text(previews[QUALITY_MAP[code]]) for code, *_ in GRADE_BUTTONS}


def _study_cards_json(request, vocabulary_ids):
    """{"<id>": thẻ} cho bộ thẻ nhúng. Mặt sau (chủ đề + ví dụ) render sẵn
    bằng chính template của trang để JS không phải chứa chuỗi hiển thị nào."""
    cards = {}
    for card in services.get_study_cards(request.user, vocabulary_ids):
        word = card.word
        cards[str(word.pk)] = {
            "id": word.pk,
            "word": word.word,
            "reading": word.reading,
            "meaning": word.meaning_vi,
            "state": card.progress.card_state if card.progress else srs.NEW,
            "comments": card.comment_count,
            "extra": render_to_string(
                "learning/_card_extra.html", {"word": word, "examples": card.examples}
            ),
            "previews": _card_previews(request, card.progress),
        }
    return cards


def _undo_payload(request):
    entry = _last_undo(request, FLOW_STUDY)
    return {"vocab": entry["vocab"], "word": entry.get("word", "")} if entry else None


def _study_seq(request, session_id):
    data = request.session.get(STUDY_SEQ_KEY) or {}
    return data.get("seq", 0) if session_id and data.get("sid") == session_id else 0


def _study_deck(request, word, scope_label):
    """Bộ thẻ nhúng vào trang học (spec.md T4.3) — trạng thái phiên y như
    request.session đang giữ + dữ liệu của tối đa DECK_BATCH thẻ sắp gặp."""
    session_id = request.session.get(STUDY_SESSION_ID_KEY)
    queue = list(request.session.get(STUDY_QUEUE_KEY) or [])
    learning_ids = request.session.get(STUDY_LEARNING_KEY) or []
    now = timezone.now()
    rows = []
    if learning_ids:
        rows = UserVocabularyProgress.objects.filter(
            user=request.user, vocabulary_id__in=learning_ids,
            card_state__in=srs.IN_SESSION_STATES,
        ).values_list("vocabulary_id", "due_at")
    learning = sorted(rows, key=lambda row: (row[1] or now, row[0]))
    upcoming = list(dict.fromkeys([word.pk, *queue, *(vid for vid, _ in learning)]))
    return {
        "session": session_id,
        "seq": _study_seq(request, session_id),
        "now": now.isoformat(),
        "current": word.pk,
        "total": request.session.get(STUDY_TOTAL_KEY) or 0,
        "touch": _touches_schedule(request),
        "queue": queue,
        "learning": [
            {"id": vid, "due": due.isoformat() if due else None} for vid, due in learning
        ],
        "seen": sorted(_first_grades(request, session_id)),
        "undo": _undo_payload(request),
        "cards": _study_cards_json(request, upcoming[:DECK_BATCH]),
        "qualities": QUALITY_MAP,
        "urls": {
            "sync": reverse("learning:study_sync"),
            "cards": reverse("learning:study_cards"),
            "discussion": reverse("learning:study_discussion", args=[0]),
            "review": reverse("learning:study_review", args=[0]),
            "panel": reverse("learning:study"),
        },
        # Mẫu câu có chỗ trống {...} — JS chỉ điền số, không tự ghép chữ.
        "text": {
            "progress": message(
                "learning.flashcard.hint.progress",
                topic=scope_label, seen="{seen}", total="{total}", done="{done}",
            ),
            "undo": message("learning.flashcard.button.undo_word", word="{word}"),
            "ahead": message("learning.flashcard.hint.learn_ahead", minutes="{minutes}"),
            "discussion": "💬 " + label("learning.flashcard.section.discussion") + " ({count})",
            "states": {state: label(f"learning.flashcard.state.{state}") for state in srs.CARD_STATES},
        },
    }


def _study_card_status(request, vocabulary_ids):
    """Trạng thái sau khi chấm của các thẻ vừa đụng tới: còn ở bước học không
    (quay lại trong phiên) và tới hạn lúc nào — đúng nguồn mà
    `_next_queue_word` dùng để xếp thẻ."""
    learning = set(request.session.get(STUDY_LEARNING_KEY) or [])
    rows = {
        p.vocabulary_id: p
        for p in UserVocabularyProgress.objects.filter(
            user=request.user, vocabulary_id__in=vocabulary_ids
        )
    }
    status = {}
    for vid in vocabulary_ids:
        progress = rows.get(vid)
        state = progress.card_state if progress else srs.NEW
        in_learning = vid in learning and state in srs.IN_SESSION_STATES
        due = progress.due_at if (in_learning and progress) else None
        status[str(vid)] = {
            "state": state,
            "learning": in_learning,
            "due": due.isoformat() if due else None,
            "previews": _card_previews(request, progress),
        }
    return status


def _parse_sync_payload(request):
    """(session_id, [(seq, op, vocab_id, quality)]) từ field `payload` (JSON).
    Gửi dạng form (không phải JSON thô) để sendBeacon mang được csrf token."""
    payload = json.loads(request.POST.get("payload") or "{}")
    session_id = int(payload.get("session") or 0)
    ops = []
    for raw in list(payload.get("ops") or [])[:SYNC_OPS_MAX]:
        ops.append((int(raw["seq"]), str(raw["op"]), int(raw["vocab"]), raw.get("quality")))
    ops.sort(key=lambda op: op[0])
    return session_id, ops


@require_POST
def study_sync_view(request):
    """Nhận một lô lệnh chấm/hoàn tác của phiên đang mở, trả JSON.

    * 401 nếu hết phiên đăng nhập (không redirect sang trang login như
      @login_required — fetch() sẽ đi theo redirect và nhận về HTML).
    * 409 nếu `session` không phải phiên đang mở (đã bắt đầu phiên khác ở tab
      khác, hoặc phiên đã kết thúc) — JS tải lại màn học.
    * Lệnh có seq <= seq đã xử lý thì bỏ qua (gửi lại sau lỗi mạng).
    * "undo" không khớp mục trên cùng của ngăn hoàn tác -> dừng, `resync`
      = true: JS bỏ các lệnh còn lại và tải lại màn học theo server.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"error": "auth", "login": reverse("accounts:login")}, status=401)
    try:
        session_id, ops = _parse_sync_payload(request)
    except (ValueError, TypeError, KeyError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    current = request.session.get(STUDY_SESSION_ID_KEY)
    if not current or session_id != current:
        return JsonResponse({"error": "session"}, status=409)

    last = _study_seq(request, current)
    touched, missing, resync = [], [], False
    for seq, kind, vocab_id, quality in ops:
        if seq <= last:
            continue
        last = seq
        if kind == "grade":
            vocab = Vocabulary.objects.filter(pk=vocab_id).first()
            if vocab is None:
                missing.append(vocab_id)
                continue
            _grade_word(request, vocab, QUALITY_MAP.get(quality, 3))
        elif kind == "undo":
            entry = _last_undo(request, FLOW_STUDY)
            if entry is None or entry["vocab"] != vocab_id:
                resync = True
                break
            _apply_undo(request)
        else:
            resync = True
            break
        touched.append(vocab_id)
    request.session[STUDY_SEQ_KEY] = {"sid": current, "seq": last}

    return JsonResponse({
        "seq": last,
        "now": timezone.now().isoformat(),
        "cards": _study_card_status(request, list(dict.fromkeys(touched))),
        "missing": missing,
        "undo": _undo_payload(request),
        "resync": resync,
    })


@login_required
def study_cards_view(request):
    """Tải thêm thẻ cho bộ thẻ nhúng: ?ids=1,2,3 (tối đa DECK_BATCH). Id của
    từ đã bị xoá không có trong kết quả — JS bỏ qua thẻ đó."""
    ids = []
    for part in (request.GET.get("ids") or "").split(",")[:DECK_BATCH]:
        if part.strip().isdigit():
            ids.append(int(part))
    return JsonResponse({"cards": _study_cards_json(request, ids)})


@login_required
def study_discussion_view(request, vocabulary_id):
    """Thân khu thảo luận của một từ — tải khi người học mở khu này ở thẻ đã
    chuyển bằng JS (bộ thẻ nhúng không mang bình luận)."""
    word = get_object_or_404(Vocabulary, pk=vocabulary_id)
    return render(request, "learning/_card_discussion_body.html", {
        "word": word,
        "comments": gamification_services.get_vocabulary_comments(word),
        "topic_slug_value": "",
        "discussion_next": reverse("learning:study"),
    })


@login_required
@require_POST
def study_retry_view(request):
    """Nút "Ôn thêm N từ này" trên màn tổng kết — một lượt ÔN THÊM gồm đúng
    các từ lần đầu bấm Quên của lượt vừa xong.

    Không đẩy lịch SM-2 (STUDY_TOUCH_SCHEDULE_KEY = False, như các phạm vi
    "ôn thêm" của SC15): lượt chính vừa xếp lịch cho các từ này rồi, ôn thêm
    chỉ để khắc sâu. Bấm Quên thì từ xuống cuối hàng đợi để gặp lại.
    """
    raw_ids = []
    for value in request.POST.getlist("vocab")[:RETRY_MAX]:
        if value.isdigit() and int(value) not in raw_ids:
            raw_ids.append(int(value))
    existing = set(Vocabulary.objects.filter(pk__in=raw_ids).values_list("pk", flat=True))
    queue = [vid for vid in raw_ids if vid in existing]
    if not queue:
        flash.error(request, message("learning.study.error.empty_queue"))
        return redirect("learning:dashboard")

    _start_study_session(request, queue, message("learning.study.scope.retry"), touch=False)
    return redirect("learning:study")


@login_required
@require_POST
def study_end_view(request):
    """Kết thúc phiên sớm — hoãn từ đang học dở sang mai, đóng StudySession và
    dọn hàng đợi."""
    postponed = _postpone_study_learning(request)
    _clear_study_session(request)
    _flash_postponed(request, postponed)
    return redirect("learning:dashboard")


def _flash_postponed(request, count):
    if count:
        flash.info(request, message("learning.study.hint.postponed", count=count))


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
        "topic_rows": [],
        "topic_pager": None,
        "memory_rows": services.get_memory_distribution(user) if active_view == REVIEW_VIEW_MEMORY else [],
        "calendar": services.get_review_calendar(user) if active_view == REVIEW_VIEW_CALENDAR else [],
    }
    if active_view == REVIEW_VIEW_TOPIC:
        # Bảng theo chủ đề dài theo số chủ đề đã học (vài chục dòng) -> phân
        # trang 5/10/20/50/100 dòng như SC05, mặc định 10 (sửa 01/10/2026).
        # Thứ tự "nợ nhiều từ đến hạn nhất lên đầu" giữ nguyên qua các trang.
        per_page = pagination.clean_per_page(request.GET.get(pagination.PER_PAGE_PARAM))
        pager = pagination.paginate(
            services.get_topic_review_rows(user),
            request.GET.get(pagination.PAGE_PARAM),
            per_page,
            keep={REVIEW_VIEW_PARAM: REVIEW_VIEW_TOPIC},
        )
        context["topic_pager"] = pager
        context["topic_rows"] = pager["page_obj"].object_list
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

    _start_study_session(
        request, queue, _review_scope_label(scope, topics),
        topic=topics[0] if len(topics) == 1 else None,
        touch=vocab_selectors.touches_schedule(scope),
        mode=mode,
    )

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
        _flash_quiz_score(request, session)
        return render(request, "learning/quiz.html", {
            "word": None, "scope_label": scope_label,
        })

    # Nhiễu lấy theo chủ đề ĐẦU TIÊN của từ (hàng đợi có thể gộp nhiều chủ
    # đề); từ không có chủ đề nào thì get_quiz_choices tự lấy từ toàn bộ từ điển.
    topic = word.topics.first()
    context = {
        "topic": topic,
        "word": word,
        **_study_progress(request, remaining),
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
