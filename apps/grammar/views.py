from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from apps.keigo.views import _pagination_query

from .models import GrammarPattern

PAGE_SIZE = 20


@login_required
def index_view(request):
    """Danh sách mẫu ngữ pháp — tìm (?q=) + lọc cấp độ (?cap=) + chương (?chuong=), đều GET."""
    query = (request.GET.get("q") or "").strip()
    level = request.GET.get("cap", "")
    category = request.GET.get("chuong", "")

    qs = GrammarPattern.objects.all()
    if query:
        qs = qs.filter(Q(pattern__icontains=query) | Q(meaning_vi__icontains=query) | Q(example_jp__icontains=query))
    if level:
        qs = qs.filter(level=level)
    if category:
        qs = qs.filter(category=category)

    paginator = Paginator(qs, PAGE_SIZE)
    context = {
        "page_obj": paginator.get_page(request.GET.get("page")),
        "paginator": paginator,
        "pagination_query": _pagination_query(request),
        "query": query,
        "level": level,
        "category": category,
        "levels": GrammarPattern.objects.exclude(level="").values_list("level", flat=True).distinct().order_by("level"),
        "categories": GrammarPattern.objects.exclude(category="").values_list("category", flat=True).distinct().order_by("category"),
        "total_count": GrammarPattern.objects.count(),
        "active_nav": "grammar",
    }
    return render(request, "grammar/index.html", context)
