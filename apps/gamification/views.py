"""
View phía NGƯỜI HỌC của tính năng góp ý — SC11_GopYTuVung.

    /contributions/                 -> tab "Gửi góp ý mới" (mặc định)
    /contributions/?tab=mine        -> tab "Góp ý của tôi"
    /contributions/?type=meaning    -> đổi loại góp ý đang soạn
    /contributions/gui/  (POST)     -> gửi

TAB VÀ LOẠI GÓP Ý LÀ LINK, KHÔNG PHẢI JAVASCRIPT. Mockup SC11 dùng
`onclick="showType(...)"` để ẩn/hiện 3 khối form; bản thật đổi sang query
string vì (1) chạy cả khi tắt JS, (2) mỗi lượt render chỉ dựng đúng MỘT form
nên lỗi validate hiện đúng chỗ thay vì nằm trong khối đang bị ẩn, (3) link
"Góp ý sửa" từ flashcard/SC05 trỏ thẳng được vào đúng loại + đúng từ
(`?type=meaning&vocabulary=<id>`).

Màn ADMIN duyệt góp ý (SC12) nằm ở apps/admin_panel/views.py — đúng quy ước
của dự án: mọi màn trong khu quản trị dùng chung sidebar + staff_required ở đó.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.properties import message
from apps.vocabulary.models import Vocabulary

from . import services
from .forms import CommentForm, EditMeaningForm, NewWordForm
from .models import Contribution

PAGE_SIZE = 20

TYPE_WORD = "word"
TYPE_MEANING = "meaning"
TYPE_COMMENT = "comment"
DEFAULT_TYPE = TYPE_WORD

# ?type= trên URL -> (form, mã loại góp ý trong MasterCode code_type 02).
FORM_BY_TYPE = {
    TYPE_WORD: (NewWordForm, services.CONTRIBUTION_TYPE_NEW_WORD),
    TYPE_MEANING: (EditMeaningForm, services.CONTRIBUTION_TYPE_EDIT_MEANING),
    TYPE_COMMENT: (CommentForm, services.CONTRIBUTION_TYPE_COMMENT),
}

TAB_NEW = "new"
TAB_MINE = "mine"


def _normalize_type(raw):
    return raw if raw in FORM_BY_TYPE else DEFAULT_TYPE


def _initial_for(type_key, request):
    """Điền sẵn từ vựng khi vào màn từ link "Góp ý sửa" (?vocabulary=<id>).

    Id rác thì lờ đi chứ không 404 — người dùng sửa URL bằng tay không đáng
    nhận trang lỗi, form vẫn dùng được bình thường.
    """
    if type_key == TYPE_WORD:
        return {}
    vocabulary_id = request.GET.get("vocabulary")
    if not vocabulary_id:
        return {}
    vocab = Vocabulary.objects.filter(pk=vocabulary_id).first()
    return {"target_vocabulary": vocab} if vocab else {}


@login_required
def contribution_view(request):
    """SC11 — form gửi góp ý + lịch sử góp ý của chính mình."""
    tab = TAB_MINE if request.GET.get("tab") == TAB_MINE else TAB_NEW
    type_key = _normalize_type(request.GET.get("type"))
    form_class, _code = FORM_BY_TYPE[type_key]

    mine = Contribution.objects.filter(user=request.user).select_related(
        "target_vocabulary", "reviewed_by"
    )
    page = Paginator(mine, PAGE_SIZE).get_page(request.GET.get("page"))

    context = {
        "form": form_class(initial=_initial_for(type_key, request)),
        "type_key": type_key,
        "tab": tab,
        "page_obj": page,
        "mine_count": page.paginator.count,
        "active_nav": "contribution",
    }
    return render(request, "gamification/contribution_form.html", context)


@login_required
@require_POST
def contribution_submit_view(request):
    """Nhận form gửi góp ý. Lỗi validate thì render lại ĐÚNG loại đang soạn."""
    type_key = _normalize_type(request.POST.get("type"))
    form_class, type_code = FORM_BY_TYPE[type_key]
    form = form_class(request.POST)

    if not form.is_valid():
        context = {
            "form": form,
            "type_key": type_key,
            "tab": TAB_NEW,
            "page_obj": Paginator(
                Contribution.objects.filter(user=request.user), PAGE_SIZE
            ).get_page(1),
            "mine_count": Contribution.objects.filter(user=request.user).count(),
            "active_nav": "contribution",
        }
        return render(request, "gamification/contribution_form.html", context)

    services.submit_contribution(request.user, type_code, **form.as_contribution_fields())
    flash.success(request, message("contribution.submit.success"))
    return redirect(f"{reverse('gamification:form')}?tab={TAB_MINE}")
