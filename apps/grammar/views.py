from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import render

from apps.keigo.views import _pagination_query

from .models import CHAPTERS, GrammarPattern, chapter_name_vi

PAGE_SIZE = 20


def _ordered_chapters():
    """[(tên chương, số mẫu)] theo thứ tự sách; chương lạ (không có trong CHAPTERS) xếp cuối."""
    counts = dict(GrammarPattern.objects.exclude(category="").values_list("category").annotate(n=Count("id")))
    order = {c: i for i, c in enumerate(CHAPTERS)}
    return sorted(counts.items(), key=lambda kv: (order.get(kv[0], len(CHAPTERS)), kv[0]))


@login_required
def index_view(request):
    """Lưới chương; có ?q= thì thành trang kết quả tìm trên cả 500 mẫu."""
    query = (request.GET.get("q") or "").strip()
    context = {"query": query, "total_count": GrammarPattern.objects.count(), "active_nav": "grammar"}
    if query:
        qs = GrammarPattern.objects.filter(
            Q(pattern__icontains=query) | Q(meaning_vi__icontains=query) | Q(example_jp__icontains=query)
        )
        paginator = Paginator(qs, PAGE_SIZE)
        context.update(
            page_obj=paginator.get_page(request.GET.get("page")),
            paginator=paginator,
            pagination_query=_pagination_query(request),
        )
    else:
        context["chapters"] = [
            {"no": i, "jp": c, "vi": chapter_name_vi(c), "count": n}
            for i, (c, n) in enumerate(_ordered_chapters(), start=1)
        ]
    return render(request, "grammar/index.html", context)


@login_required
def chapter_view(request, category):
    """Một chương (~16 mẫu) trên một trang — không phân trang; có nút chương trước/sau."""
    patterns = list(GrammarPattern.objects.filter(category=category))
    if not patterns:
        raise Http404
    names = [c for c, _ in _ordered_chapters()]
    i = names.index(category)
    context = {
        "patterns": patterns,
        "no": i + 1,
        "jp": category,
        "vi": chapter_name_vi(category),
        "prev": names[i - 1] if i > 0 else None,
        "next": names[i + 1] if i + 1 < len(names) else None,
        "active_nav": "grammar",
    }
    return render(request, "grammar/chapter.html", context)
