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

Cùng app còn có SC13_ThanhTich (Điểm & Danh hiệu):

    /contributions/thanh-tich/                      -> trang điểm & danh hiệu
    /contributions/thanh-tich/ghim/<code_type>/     -> POST ghim 1 nhóm danh hiệu
    /contributions/thanh-tich/bo-ghim/<code_type>/  -> POST bỏ ghim

SC13 ở đây chứ không phải app riêng vì điểm và danh hiệu đều sinh ra từ luồng
góp ý (apps.gamification.services.award_points) — tách ra sẽ thành một app chỉ
có view mà không có model nào của mình.

Màn ADMIN duyệt góp ý (SC12) nằm ở apps/admin_panel/views.py — đúng quy ước
của dự án: mọi màn trong khu quản trị dùng chung sidebar + staff_required ở đó.
"""
from django.contrib import messages as flash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.core.properties import message
from apps.vocabulary.models import Vocabulary

from . import services
from .forms import CommentForm, EditMeaningForm, NewWordForm
from .models import BadgeCategory, Contribution

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


# Tên field ẩn mang pk của từ bị khoá. CỐ Ý tách khỏi `target_vocabulary`:
# nếu lấy luôn giá trị của chính ô đó thì sửa nó trên DevTools là "đổi được từ
# khác" — vì lượt POST sẽ khoá theo đúng cái vừa bị sửa. Tách ra thì queryset
# của form thu về đúng từ đã khoá và mọi giá trị khác bị validate đánh trượt.
LOCK_FIELD = "locked_vocabulary"


def _locked_vocabulary(request, type_key):
    """Từ vựng bị KHOÁ cho lượt góp ý này, hoặc None.

    Vào màn từ link "Góp ý" ở flashcard/SC05 thì người dùng đang nói về ĐÚNG từ
    đó, nên ô chọn từ bị khoá lại: không đổi sang từ khác được (xem
    `_TargetedForm` bên forms.py). Muốn góp ý cho từ khác thì vào màn Góp ý từ
    thanh menu — ở đó ô chọn mở bình thường.

    GET lấy từ `?vocabulary=`, POST lấy từ field ẩn `locked_vocabulary` mà
    template gửi kèm, để lượt render lại sau khi validate lỗi vẫn giữ nguyên
    trạng thái khoá.

    Id rác thì lờ đi chứ không 404 — người dùng sửa URL bằng tay không đáng
    nhận trang lỗi, form chỉ đơn giản mở lại ô chọn.
    """
    if type_key == TYPE_WORD:
        return None  # "Từ mới" không gắn với từ nào sẵn có

    if request.method == "POST":
        vocabulary_id = request.POST.get(LOCK_FIELD)
    else:
        vocabulary_id = request.GET.get("vocabulary")

    if not vocabulary_id:
        return None
    return Vocabulary.objects.filter(pk=vocabulary_id).first()


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

    locked = _locked_vocabulary(request, type_key)
    context = {
        "form": form_class(locked_vocabulary=locked),
        "type_key": type_key,
        "tab": tab,
        "locked_vocabulary": locked,
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
    locked = _locked_vocabulary(request, type_key)
    form = form_class(request.POST, locked_vocabulary=locked)

    if not form.is_valid():
        context = {
            "form": form,
            "type_key": type_key,
            "tab": TAB_NEW,
            "locked_vocabulary": locked,
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


# --------------------------------------------------------------------------
# SC13_ThanhTich — Điểm & Danh hiệu
# --------------------------------------------------------------------------

@login_required
def achievements_view(request):
    """
    SC13 — điểm, danh hiệu từng nhóm, lịch sử điểm, bảng xếp hạng.

    Toàn bộ số liệu tính ở apps.gamification.services (get_all_category_progress
    / get_point_history / get_leaderboard), view chỉ lắp vào context — cùng
    cách chia việc như apps.accounts.views.profile_view.

    Khác mockup một chỗ: mockup chỉ vẽ MỘT nhóm danh hiệu ("5 bậc danh hiệu"),
    bản thật vẽ mọi BadgeCategory đang bật, vì mô hình đã là nhiều nhóm
    (Đóng góp / Học tập / Kiểm tra — xem docs/SPEC_GOP_Y_THANH_TICH.md mục 5)
    và mỗi nhóm cần nút ghim riêng.
    """
    progress_list = services.get_all_category_progress(request.user)

    context = {
        "progress_list": progress_list,
        "highlight": services.get_highlight_progress(progress_list),
        "total_points": request.user.total_points,
        "contribution_stats": services.get_contribution_stats(request.user),
        "rank": services.get_contribution_rank(request.user),
        "point_history": services.get_point_history(request.user),
        "leaderboard": services.get_leaderboard(current_user=request.user),
        "max_pinned": services.MAX_PINNED_BADGES,
        "pinned_count": sum(1 for item in progress_list if item["is_pinned"]),
        "active_nav": "contribution",
    }
    return render(request, "gamification/achievements.html", context)


def _active_category(code_type):
    """Nhóm danh hiệu đang bật theo code_type, 404 nếu không có.

    404 chứ không lờ đi như `?vocabulary=` rác bên SC11: ở đây code_type nằm
    trong URL của một form POST do chính trang dựng ra, sai nghĩa là dữ liệu
    đã lệch chứ không phải người dùng gõ tay.
    """
    return get_object_or_404(BadgeCategory, code_type=code_type, is_active=True)


@login_required
@require_POST
def pin_badge_view(request, code_type):
    """Ghim 1 nhóm danh hiệu lên hồ sơ. Lỗi nghiệp vụ (chưa đạt bậc nào / đã
    ghim đủ số lượng) do services.pin_badge ném ra dưới dạng ValueError kèm
    sẵn message đã tra từ message.properties."""
    category = _active_category(code_type)
    try:
        services.pin_badge(request.user, category)
    except ValueError as exc:
        flash.error(request, str(exc))
    else:
        flash.success(
            request, message("badge.pin.success", badge_name=_badge_name(request.user, category))
        )
    return redirect("gamification:achievements")


@login_required
@require_POST
def unpin_badge_view(request, code_type):
    category = _active_category(code_type)
    # Lấy TÊN TRƯỚC khi bỏ ghim — sau đó bản ghi không còn, thông báo sẽ trống.
    badge_name = _badge_name(request.user, category)
    services.unpin_badge(request.user, category)
    flash.success(request, message("badge.unpin.success", badge_name=badge_name))
    return redirect("gamification:achievements")


def _badge_name(user, category):
    """Tên bậc user đang đạt ở nhóm này, lùi về tên nhóm nếu chưa đạt bậc nào."""
    tier, _value = services.get_earned_tier(user, category)
    return category.tier_name(tier.code) if tier else category.name
