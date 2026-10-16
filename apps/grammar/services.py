"""Logic học/kiểm tra ngữ pháp — view chỉ lắp context (spec.md rule 6)."""
import random
import re

from django.db.models import Count
from django.utils import timezone

from .models import CHAPTERS, GrammarPattern, UserGrammarProgress

BLANK = "（　　）"
_PARENS = re.compile(r"\(.*?\)|（.*?）")
_SEPS = re.compile(r"[・/／、…]")


def ordered_chapters():
    """[(tên chương, số mẫu)] theo thứ tự sách; chương lạ (không có trong CHAPTERS) xếp cuối."""
    counts = dict(GrammarPattern.objects.exclude(category="").values_list("category").annotate(n=Count("id")))
    order = {c: i for i, c in enumerate(CHAPTERS)}
    return sorted(counts.items(), key=lambda kv: (order.get(kv[0], len(CHAPTERS)), kv[0]))


def mastered_by_chapter(user):
    """{chương: số mẫu đã thuộc} của user."""
    return dict(
        UserGrammarProgress.objects.filter(user=user, is_mastered=True)
        .values_list("pattern__category").annotate(n=Count("id"))
    )


def mastered_ids(user, patterns):
    return set(
        UserGrammarProgress.objects.filter(user=user, is_mastered=True, pattern__in=patterns)
        .values_list("pattern_id", flat=True)
    )


def display_form(pattern):
    """'〜につけ(て)' -> 'につけ(て)' — chữ hiện trên nút lựa chọn."""
    return pattern.lstrip("〜～")


def _cores(pattern):
    """Các dạng có thể xuất hiện nguyên văn trong câu ví dụ, dài trước: '〜ぬきで／〜ぬきに(は)' -> [...]."""
    text = _PARENS.sub("", pattern)
    parts = [p.strip("〜～ ") for p in _SEPS.split(text)]
    return sorted({p for p in parts if p}, key=len, reverse=True)


def build_question(pattern, chapter_patterns):
    """Một câu hỏi 4 lựa chọn cho `pattern`, đáp án nhiễu lấy từ cùng chương.

    Kiểu 'cloze': che dạng mẫu trong câu ví dụ (khớp được 437/500 mẫu). Mẫu chia động từ
    không khớp chữ thì hỏi kiểu 'meaning': cho nghĩa, chọn mẫu.
    Seed theo pattern.id để tải lại trang không đổi thứ tự lựa chọn."""
    rng = random.Random(pattern.id)
    others = [p for p in chapter_patterns if p.id != pattern.id]
    options = rng.sample(others, min(3, len(others))) + [pattern]
    rng.shuffle(options)

    prompt, kind = pattern.meaning_vi, "meaning"
    for core in _cores(pattern.pattern):
        if core in pattern.example_jp:
            prompt, kind = pattern.example_jp.replace(core, BLANK, 1), "cloze"
            break
    return {
        "kind": kind,
        "prompt": prompt,
        "options": [{"id": o.id, "text": display_form(o.pattern)} for o in options],
        "answer_id": pattern.id,
    }


def record_answer(user, pattern, is_correct):
    """Đúng -> đã thuộc; sai -> bỏ đánh dấu đã thuộc (phải học lại mẫu đó)."""
    progress, _ = UserGrammarProgress.objects.get_or_create(user=user, pattern=pattern)
    progress.is_mastered = is_correct
    if is_correct:
        progress.correct_count += 1
    else:
        progress.wrong_count += 1
    progress.last_answered_at = timezone.now()
    progress.save()
    return progress
