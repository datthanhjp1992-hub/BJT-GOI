"""
View của app learning: SC03 Trang chủ · SC04 Flashcard · SC06 Kiểm tra.

Mọi truy vấn thống kê nằm ở `apps.learning.services`; view chỉ lắp context.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.constants import CODE_TYPE_BJT_LEVEL
from apps.vocabulary.models import Vocabulary

from . import services
from .models import UserVocabularyProgress
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
        "bjt_level_code_type": CODE_TYPE_BJT_LEVEL,
        "active_nav": "home",
    }
    return render(request, "learning/dashboard.html", context)


@login_required
def flashcard_view(request, topic_slug):
    """SC04_HocTuVung."""
    words = Vocabulary.objects.filter(topics__slug=topic_slug)
    return render(
        request, "learning/flashcard.html", {"words": words, "topic_slug": topic_slug}
    )


@login_required
def flashcard_review(request, vocabulary_id):
    """Endpoint POST của 4 nút Quên/Khó/Nhớ/Dễ trên màn flashcard."""
    vocab = get_object_or_404(Vocabulary, pk=vocabulary_id)
    progress, _ = UserVocabularyProgress.objects.get_or_create(
        user=request.user, vocabulary=vocab
    )
    quality_key = request.POST.get("quality")
    review_word(progress, QUALITY_MAP.get(quality_key, 3))
    return redirect("learning:flashcard", topic_slug=request.POST.get("topic_slug"))


@login_required
def quiz_view(request, topic_slug):
    """SC06_KiemTra."""
    words = Vocabulary.objects.filter(topics__slug=topic_slug)
    return render(request, "learning/quiz.html", {"words": words})
