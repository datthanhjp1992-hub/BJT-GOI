"""
View cua app keigo -- SC16 (muc luc) + SC18 (bang tra dong tu).

Giai doan 1 chi co noi dung kinh ngu (khong co bai tap) -- SC17/SC19-22 CHUA
lam, xem claude/keigo-thiet-ke.md muc 7 va muc 8. Chuong nao chua co trang bai
hoc (SC17) thi the tren SC16 hien dang "sap co", KHONG dan toi 404 -- dung
quyet dinh 4 da ghi trong htmlTemplate/SC16_KinhNguMucLuc_A.html.

Ban quyen PDF (Thaolejp / HCC JAPAN) CHUA xin phep -- xem keigo-thiet-ke.md
muc 0. Cho toi khi Dat quyet, ca khu kinh ngu doi dang nhap, coi nhu tai lieu
hoc noi bo thay vi cong khai roi phai khoa lai sau.
"""
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import QueryDict
from django.shortcuts import get_object_or_404, render

from apps.core.properties import label

from . import selectors
from .models import KeigoForm, KeigoLesson, KeigoPattern, KeigoVerb

# Chuong duy nhat KHONG co trang bai hoc rieng -- no dan thang sang bang tra.
# Xem ghi chu 3 o dau htmlTemplate/SC16_KinhNguMucLuc_A.html.
VERB_TABLE_LESSON_SLUG = "bang-chia-dong-tu-bat-quy-tac"

# Bang 4 cot ma moi o co toi 4 dong thi rat dai -- 10 dong/trang du xem het
# 47 dong trong 5 trang, khong phai cuon qua nhieu.
PAGE_SIZE = 10


def _lesson_meta_text(lesson):
    """Dong "N mau ngu phap * N vi du * N cap tu" -- chi phan nao > 0 moi hien,
    tinh o Python thay vi lam 3 nhanh {% if %} noi nhau trong template."""
    parts = []
    if lesson.pattern_count:
        parts.append(f"{lesson.pattern_count} {label('keigo.index.lesson.pattern_count')}")
    if lesson.example_count:
        parts.append(f"{lesson.example_count} {label('keigo.index.lesson.example_count')}")
    if lesson.phrase_pair_count:
        parts.append(f"{lesson.phrase_pair_count} {label('keigo.index.lesson.pair_count')}")
    return " \u00b7 ".join(parts)


def _pagination_query(request):
    """Chuoi query giu lai q/loai/batquytac khi bam sang trang khac -- copy
    nguyen GET hien tai, chi bo `page`. Don gian hon
    apps/vocabulary/views.py._pagination_query() vi khong can chuan hoa lai
    gia tri, chi can mang nguyen ve."""
    params = QueryDict(mutable=True)
    params.update(request.GET)
    params.pop("page", None)
    encoded = params.urlencode()
    return ("&" + encoded) if encoded else ""


@login_required
def index_view(request):
    """SC16_KinhNguMucLuc."""
    lessons = list(
        KeigoLesson.objects.annotate(
            pattern_count=Count("patterns", distinct=True),
            example_count=Count("patterns__examples", distinct=True),
            phrase_pair_count=Count("phrase_pairs", distinct=True),
        )
    )
    for lesson in lessons:
        lesson.meta_text = _lesson_meta_text(lesson)
    totals = {
        "verb_count": KeigoVerb.objects.count(),
        "form_count": KeigoForm.objects.count(),
        "pattern_count": KeigoPattern.objects.count(),
    }
    context = {
        "lessons": lessons,
        "totals": totals,
        "verb_table_lesson_slug": VERB_TABLE_LESSON_SLUG,
        "active_nav": "keigo",
        "active_sub": "index",  # to dung muc "Muc luc" trong sidebar
    }
    return render(request, "keigo/index.html", context)


@login_required
def verb_lookup_view(request):
    """SC18_TraCuuDongTu -- loc + tim bang GET, khong bat buoc JavaScript.

    Phan trang PAGE_SIZE dong/trang -- bang 4 cot ma moi o co toi 4 dang thi
    47 dong roi ra rat dai. attach_columns() chi chay tren ĐUNG trang hien
    tai (page.object_list), khong phai toan bo verbs khop loc."""
    query = (request.GET.get(selectors.SEARCH_PARAM) or "").strip()
    style = selectors.clean_style(request.GET.get(selectors.STYLE_PARAM, ""))
    irregular_only = request.GET.get(selectors.IRREGULAR_PARAM) == "1"

    verbs_qs = selectors.filter_verbs(query=query, style=style, irregular_only=irregular_only)
    paginator = Paginator(verbs_qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))
    page.object_list = selectors.attach_columns(page.object_list)

    context = {
        "page_obj": page,
        "paginator": paginator,
        "pagination_query": _pagination_query(request),
        "query": query,
        "style": style,
        "irregular_only": irregular_only,
        "style_choices": selectors.style_filter_choices(),
        "total_verb_count": KeigoVerb.objects.count(),
        "active_nav": "keigo",
        "active_sub": "tra_cuu",  # to dung muc "Tra cuu tu" trong sidebar
    }
    return render(request, "keigo/tra_cuu.html", context)


@login_required
def verb_detail_view(request, pk):
    """Chi tiet mot dong tu -- trang RIENG (khong phai <details>) de chia se
    va de trang tu vung tro nguoc ve, xem ghi chu o cuoi
    htmlTemplate/SC18_TraCuuDongTu_A.html."""
    verb = get_object_or_404(KeigoVerb.objects.prefetch_related("forms"), pk=pk)
    verb = selectors.attach_columns([verb])[0]
    context = {"verb": verb, "active_nav": "keigo", "active_sub": "tra_cuu"}
    return render(request, "keigo/verb_detail.html", context)
