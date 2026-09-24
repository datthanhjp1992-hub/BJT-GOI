"""
View cua app keigo -- SC16 (muc luc) + SC17 (bai hoc) + SC18 (bang tra dong tu)
+ SC19 (loi thuong gap).

SC20-22 CHUA lam, xem claude/keigo-thiet-ke.md muc 7 va muc 8. Chuong nao
khong co noi dung (meta_text rong) thi the tren SC16 van hien dang "sap co",
KHONG dan toi 404 -- dung quyet dinh 4 trong htmlTemplate/SC16_KinhNguMucLuc_A.html.

Ban quyen PDF (Thaolejp / HCC JAPAN) CHUA xin phep -- xem keigo-thiet-ke.md
muc 0. Cho toi khi Dat quyet, ca khu kinh ngu doi dang nhap, coi nhu tai lieu
hoc noi bo thay vi cong khai roi phai khoa lai sau.
"""
import logging

from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode

from apps.core.properties import label, message

from . import pdf as keigo_pdf
from . import selectors
from .models import KeigoForm, KeigoLesson, KeigoPattern, KeigoVerb

logger = logging.getLogger(__name__)

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


def lesson_url(lesson):
    """URL "mo chuong nay" -- chuong bang chia dong tu di thang sang SC18."""
    if lesson.slug == VERB_TABLE_LESSON_SLUG:
        return reverse("keigo:tra_cuu")
    return reverse("keigo:lesson", args=[lesson.slug])


def _lesson_position(lesson):
    """(tat ca chuong theo thu tu, vi tri 0-based cua `lesson`)."""
    lessons = list(KeigoLesson.objects.order_by("display_order", "slug"))
    position = next(i for i, x in enumerate(lessons) if x.pk == lesson.pk)
    return lessons, position


@login_required
def learn_start_view(request):
    """Muc "Hoc tu" o sidebar -- vao chuong dau tien co trang bai hoc. La
    redirect chu khong hardcode slug trong sidebar.html, de doi thu tu chuong
    qua SC07b khong phai sua template."""
    lesson = (KeigoLesson.objects.exclude(slug=VERB_TABLE_LESSON_SLUG)
              .order_by("display_order", "slug").first())
    if lesson is None:
        return redirect("keigo:index")
    return redirect("keigo:lesson", slug=lesson.slug)


@login_required
def lesson_view(request, slug):
    """SC17_BaiHoc -- phuong an 3: danh sach muc ben trai, moi lan hien MOT
    muc; truoc/sau la link GET ?muc=<key>. Het muc cuoi thi "tiep" dan sang
    chuong sau. Xem selectors.lesson_items()."""
    lesson = get_object_or_404(KeigoLesson, slug=slug)
    if lesson.slug == VERB_TABLE_LESSON_SLUG:
        return redirect("keigo:tra_cuu")

    base_url = reverse("keigo:lesson", args=[lesson.slug])
    items = selectors.lesson_items(lesson)
    for item in items:
        item.url = f"{base_url}?{urlencode({selectors.LESSON_ITEM_PARAM: item.key})}"

    lessons, position = _lesson_position(lesson)
    prev_lesson = lessons[position - 1] if position > 0 else None
    next_lesson = lessons[position + 1] if position + 1 < len(lessons) else None
    for other in (prev_lesson, next_lesson):
        if other is not None:
            other.url = lesson_url(other)

    index, current = None, None
    prev_item = next_item = None
    if items:
        index, current = selectors.pick_item(items, request.GET.get(selectors.LESSON_ITEM_PARAM, ""))
        selectors.load_item_detail(lesson, current)
        prev_item = items[index - 1] if index > 0 else None
        next_item = items[index + 1] if index + 1 < len(items) else None

    context = {
        "lesson": lesson,
        "lesson_number": position + 1,
        "lesson_total": len(lessons),
        "stats": selectors.lesson_stats(lesson),
        "items": items,
        "current": current,
        "position": (index + 1) if items else 0,
        "pattern_total": sum(1 for i in items if i.kind == selectors.KIND_PATTERN),
        "prev_item": prev_item,
        "next_item": next_item,
        "prev_lesson": prev_lesson,
        "next_lesson": next_lesson,
        "active_nav": "keigo",
        "active_sub": "hoc_tu",  # to dung muc "Hoc tu" trong sidebar
    }
    return render(request, "keigo/lesson.html", context)


@login_required
def lesson_pdf_view(request, slug):
    """Nut "In on tap chuong nay" o SC17 -- PDF TOAN BO noi dung chuong.

    GET, khong ghi gi vao DB nen la link <a> binh thuong. Tra `inline` de
    trinh duyet mo san trong tab moi: xem, in giay hay luu file deu duoc.
    Sinh moi moi lan (vai tram dong, duoi 1 giay), khong luu vao MEDIA_ROOT --
    MEDIA_ROOT tren Render la ephemeral, va du lieu sua qua SC07b thi PDF tu
    cap nhat theo."""
    lesson = get_object_or_404(KeigoLesson, slug=slug)
    if lesson.slug == VERB_TABLE_LESSON_SLUG:
        return redirect("keigo:tra_cuu")
    lessons, position = _lesson_position(lesson)
    try:
        data = keigo_pdf.build_lesson_pdf(lesson, position + 1, len(lessons))
    except keigo_pdf.KeigoPdfFontError:
        logger.exception("Thieu font khi sinh PDF on tap kinh ngu")
        flash.error(request, message("keigo.pdf.error.font_missing"))
        return redirect("keigo:lesson", slug=lesson.slug)
    response = HttpResponse(data, content_type="application/pdf")
    filename = keigo_pdf.lesson_pdf_filename(lesson, position + 1)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def _pitfall_url(view, check, query=""):
    """URL SC19 giu ?an=1 khi doi tab / bo tim kiem."""
    params = {selectors.PITFALL_VIEW_PARAM: view}
    if query:
        params[selectors.SEARCH_PARAM] = query
    if check:
        params[selectors.PITFALL_CHECK_PARAM] = "1"
    return f"{reverse('keigo:loi_thuong_gap')}?{urlencode(params)}"


@login_required
def pitfall_view(request):
    """SC19_LoiThuongGap -- 87 cap tu KeigoPhrasePair gom theo pair_type.

    Tab ?view=, tim ?q= (quet ca 8 nhom), tu kiem tra ?an=1 -- tat ca la GET,
    khong JavaScript. Xem selectors.pitfall_page() va 7 quyet dinh o dau
    htmlTemplate/SC19_LoiThuongGap_A.html."""
    query = (request.GET.get(selectors.SEARCH_PARAM) or "").strip()
    check = request.GET.get(selectors.PITFALL_CHECK_PARAM) == "1"
    data = selectors.pitfall_page(view=request.GET.get(selectors.PITFALL_VIEW_PARAM, ""), query=query)

    # "Xem trong chuong N" -- N la VI TRI chuong (giong "Chuong N / 7" o SC17),
    # link toi dung muc cap-<pair_type> cua SC17.
    positions = {pk: i for i, pk in enumerate(
        KeigoLesson.objects.order_by("display_order", "slug").values_list("pk", flat=True), start=1)}
    for t in data["types"]:
        t.url = _pitfall_url(t.code, check)
    for t in data["shown"]:
        if t.lesson is not None:
            t.lesson_number = positions.get(t.lesson.pk, 0)
            t.lesson_url = (f"{reverse('keigo:lesson', args=[t.lesson.slug])}?"
                            f"{urlencode({selectors.LESSON_ITEM_PARAM: selectors.PAIR_ITEM_PREFIX + t.code})}")

    context = {
        **data,
        "query": query,
        "check": check,
        "clear_url": _pitfall_url(data["view"], check),
        "check_toggle_url": _pitfall_url(data["view"], not check, query),
        "active_nav": "keigo",
        "active_sub": "loi_thuong_gap",  # to dung muc "Loi thuong gap" trong sidebar
    }
    return render(request, "keigo/loi_thuong_gap.html", context)
