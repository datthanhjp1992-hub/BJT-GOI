"""
View của app learning: SC03 Trang chủ · SC04 Flashcard · SC06 Kiểm tra.

Mọi truy vấn thống kê nằm ở `apps.learning.services`; view chỉ lắp context.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.constants import SESSION_TYPE_FLASHCARD, SESSION_TYPE_QUIZ
from apps.core.properties import message
from apps.gamification.models import Contribution
from apps.gamification.services import CONTRIBUTION_TYPE_COMMENT, STATUS_APPROVED
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
        return render(request, "learning/flashcard.html", {"topic": topic, "word": None})

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
        Contribution.objects.create(
            user=request.user,
            contribution_type_code=CONTRIBUTION_TYPE_COMMENT,
            target_vocabulary=vocab,
            comment_text=text,
        )
        flash.success(request, message("learning.flashcard.success.comment_submitted"))
    else:
        flash.error(request, message("common.validation.required"))
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
