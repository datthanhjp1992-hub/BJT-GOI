"""
View của app learning: SC03 Trang chủ · SC04 Flashcard · SC06 Kiểm tra.

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
from apps.core.properties import message
from apps.gamification.models import Contribution
from apps.gamification import services as gamification_services
from apps.gamification.services import CONTRIBUTION_TYPE_COMMENT, STATUS_APPROVED
from apps.vocabulary import selectors as vocab_selectors
from apps.vocabulary.models import Topic, Vocabulary

from . import services
from .models import StudySession, UserVocabularyProgress
from .services import QUALITY_MAP, review_word


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
    topic_slug nên user học nhiều chủ đề (tab khác nhau) không đụng nhau."""
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


@login_required
def flashcard_view(request, topic_slug):
    """SC04_HocTuVung — 1 thẻ mỗi lần, ưu tiên từ đến hạn ôn rồi tới từ chưa
    học. Xem apps.learning.services.get_flashcard_queue để biết vì sao không
    cần tự loại thẻ vừa ôn ra khỏi hàng đợi."""
    topic = get_object_or_404(Topic, slug=topic_slug)
    total_key, session_id_key = _flashcard_session_keys(topic.slug)
    queue = services.get_flashcard_queue(request.user, topic)

    if not queue:
        # Hết thẻ cần ôn (hoặc chủ đề chưa có từ nào) — đóng phiên đang mở và
        # dọn khoá session để lần mở lại sau tính là một lượt ôn mới.
        _close_flashcard_session(request, session_id_key)
        request.session.pop(total_key, None)
        return render(request, "learning/flashcard.html", {
            "topic": topic, "word": None, "scope_label": topic.display_name,
        })

    total = request.session.get(total_key)
    if not total or len(queue) > total:
        # Chưa từng mở màn này (chưa có tổng), hoặc hàng đợi vừa dài ra so với
        # lần tính trước (có thêm từ đến hạn/được thêm mới) — bắt đầu một
        # phiên StudySession mới, tính lại tổng từ đây.
        total = len(queue)
        request.session[total_key] = total
        study_session = StudySession.objects.create(
            user=request.user, topic=topic, session_type=SESSION_TYPE_FLASHCARD,
            started_at=timezone.now(),
        )
        request.session[session_id_key] = study_session.pk

    word = queue[0]
    position = total - len(queue) + 1

    context = {
        "topic": topic,
        "word": word,
        "position": position,
        "total": total,
        "percent": round((position - 1) * 100 / total) if total else 0,
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
    }
    return render(request, "learning/flashcard.html", context)


@login_required
@require_POST
def flashcard_review(request, vocabulary_id):
    """Endpoint POST của 4 nút Quên/Khó/Nhớ/Dễ trên màn flashcard."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    topic_slug = request.POST.get("topic_slug", "")
    quality = QUALITY_MAP.get(request.POST.get("quality"), 3)

    progress, _ = UserVocabularyProgress.objects.get_or_create(
        user=request.user, vocabulary=vocab
    )
    review_word(progress, quality)

    _, session_id_key = _flashcard_session_keys(topic_slug)
    session_id = request.session.get(session_id_key)
    if session_id:
        # quality >= 3 ("Khó"/"Nhớ"/"Dễ") tính là nhớ đúng, khớp ngưỡng SM-2
        # review_word() đang dùng để tăng srs_level.
        StudySession.objects.filter(pk=session_id).update(
            words_reviewed=F("words_reviewed") + 1,
            correct_answers=F("correct_answers") + (1 if quality >= 3 else 0),
        )
    return redirect("learning:flashcard", topic_slug=topic_slug)


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
    (`services.get_flashcard_queue`): từ đến hạn ôn trước, hết thì tới từ
    chưa học. Bấm thẳng vào 1 đáp án là nộp câu đó luôn (xem
    `quiz_answer_view`) — không có bước "xác nhận" riêng như mockup tĩnh,
    cùng ngôn ngữ thiết kế với 4 nút Quên/Khó/Nhớ/Dễ ở SC04."""
    topic = get_object_or_404(Topic, slug=topic_slug)
    total_key, session_id_key = _quiz_session_keys(topic.slug)
    queue = services.get_flashcard_queue(request.user, topic)

    if not queue:
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
        return render(request, "learning/quiz.html", {"topic": topic, "word": None})

    total = request.session.get(total_key)
    if not total or len(queue) > total:
        total = len(queue)
        request.session[total_key] = total
        study_session = StudySession.objects.create(
            user=request.user, topic=topic, session_type=SESSION_TYPE_QUIZ,
            started_at=timezone.now(),
        )
        request.session[session_id_key] = study_session.pk

    word = queue[0]
    position = total - len(queue) + 1

    context = {
        "topic": topic,
        "word": word,
        "position": position,
        "total": total,
        "percent": round((position - 1) * 100 / total) if total else 0,
        "choices": services.get_quiz_choices(word, topic),
    }
    return render(request, "learning/quiz.html", context)


@login_required
@require_POST
def quiz_answer_view(request, topic_slug, vocabulary_id):
    """Nộp 1 câu trắc nghiệm — mỗi nút đáp án ở quiz.html POST thẳng vào đây.
    Đúng/sai quy đổi sang quality SM-2 (4 = nhớ tốt, 0 = quên) rồi dùng lại
    NGUYÊN `review_word()` của SC04 — quiz và flashcard cùng một cơ chế SRS."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    is_correct = request.POST.get("choice") == str(vocab.pk)
    quality = 4 if is_correct else 0

    progress, _ = UserVocabularyProgress.objects.get_or_create(
        user=request.user, vocabulary=vocab
    )
    review_word(progress, quality)

    _, session_id_key = _quiz_session_keys(topic_slug)
    session_id = request.session.get(session_id_key)
    if session_id:
        StudySession.objects.filter(pk=session_id).update(
            words_reviewed=F("words_reviewed") + 1,
            correct_answers=F("correct_answers") + (1 if is_correct else 0),
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


def _clear_study_session(request):
    request.session.pop(STUDY_QUEUE_KEY, None)
    request.session.pop(STUDY_TOTAL_KEY, None)
    request.session.pop(STUDY_SCOPE_KEY, None)
    return _close_study_session(request, STUDY_SESSION_ID_KEY)


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
    request.session[STUDY_TOTAL_KEY] = len(queue)
    request.session[STUDY_SESSION_ID_KEY] = study_session.pk
    request.session[STUDY_SCOPE_KEY] = _scope_label(topics)
    return redirect("learning:study")


@login_required
def study_view(request):
    """Màn học một thẻ của phiên theo bộ lọc — dùng CHUNG template với SC04."""
    queue = list(request.session.get(STUDY_QUEUE_KEY) or [])
    total = request.session.get(STUDY_TOTAL_KEY) or len(queue)
    scope_label = request.session.get(STUDY_SCOPE_KEY) or message("learning.study.scope.all")

    word = None
    while queue and word is None:
        # Từ có thể đã bị xoá sau khi hàng đợi được chốt — bỏ qua, đừng 404
        # giữa lúc người ta đang học.
        word = Vocabulary.objects.filter(pk=queue[0]).first()
        if word is None:
            queue.pop(0)
            request.session[STUDY_QUEUE_KEY] = queue

    if word is None:
        _clear_study_session(request)
        return render(request, "learning/flashcard.html", {
            "word": None, "scope_label": scope_label, "is_study_session": True,
        })

    position = total - len(queue) + 1
    context = {
        "topic": None,
        "word": word,
        "position": position,
        "total": total,
        "percent": round((position - 1) * 100 / total) if total else 0,
        "scope_label": scope_label,
        "review_action": reverse("learning:study_review", args=[word.pk]),
        "topic_slug_value": "",
        "is_study_session": True,
        "examples": word.examples.all()[:3],
        "comments": Contribution.objects.filter(
            target_vocabulary=word,
            contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            status_code=STATUS_APPROVED,
        ).order_by("-created_at"),
    }
    return render(request, "learning/flashcard.html", context)


@login_required
@require_POST
def study_review_view(request, vocabulary_id):
    """4 nút Quên/Khó/Nhớ/Dễ của phiên học theo bộ lọc."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    quality = QUALITY_MAP.get(request.POST.get("quality"), 3)

    progress, _ = UserVocabularyProgress.objects.get_or_create(
        user=request.user, vocabulary=vocab
    )
    review_word(progress, quality)

    session_id = request.session.get(STUDY_SESSION_ID_KEY)
    if session_id:
        StudySession.objects.filter(pk=session_id).update(
            words_reviewed=F("words_reviewed") + 1,
            correct_answers=F("correct_answers") + (1 if quality >= 3 else 0),
        )

    # Bỏ đúng từ vừa ôn khỏi hàng đợi (không dựa vào vị trí đầu: người dùng
    # bấm nút hai lần / back rồi gửi lại vẫn không làm lệch hàng đợi).
    queue = list(request.session.get(STUDY_QUEUE_KEY) or [])
    if vocab.pk in queue:
        queue.remove(vocab.pk)
        request.session[STUDY_QUEUE_KEY] = queue
    return redirect("learning:study")


@login_required
@require_POST
def study_end_view(request):
    """Kết thúc phiên sớm — đóng StudySession và dọn hàng đợi."""
    _clear_study_session(request)
    return redirect("learning:dashboard")
