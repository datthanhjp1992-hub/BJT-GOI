"""
Logic tính bậc danh hiệu hiện tại của user theo từng BadgeCategory, và cơ chế
cho user tự ghim (pin) danh hiệu muốn hiển thị — thay vì hệ thống luôn tự
chọn danh hiệu điểm cao nhất.

Đặt tách khỏi models.py theo convention của apps.learning.services (thuật
toán SM-2) trong project này — model chỉ mô tả dữ liệu, service chứa nghiệp
vụ/tính toán.
"""
from apps.gamification.models import BadgeCategory, UserPinnedBadge

MAX_PINNED_BADGES = 3


def get_metric_value(user, category):
    """Tính giá trị hiện tại của user theo đại lượng (metric) của 1 category."""
    if category.metric == BadgeCategory.METRIC_CONTRIBUTION_POINTS:
        return user.total_points

    if category.metric == BadgeCategory.METRIC_WORDS_LEARNED:
        from apps.learning.models import UserVocabularyProgress
        return UserVocabularyProgress.objects.filter(user=user, is_mastered=True).count()

    if category.metric == BadgeCategory.METRIC_QUIZ_HIGH_SCORE_COUNT:
        from apps.learning.models import StudySession
        # "Đạt điểm cao" tạm định nghĩa: quiz session có >= 80% câu đúng.
        # Cần words_reviewed > 0 để tránh chia 0 với session chưa hoàn thành.
        sessions = StudySession.objects.filter(user=user, session_type="quiz", words_reviewed__gt=0)
        high_score_count = sum(
            1 for s in sessions if (s.correct_answers / s.words_reviewed) >= 0.8
        )
        return high_score_count

    return 0


def get_earned_tier(user, category):
    """Bậc CAO NHẤT user đã đạt trong 1 category, kèm giá trị hiện tại.
    Trả (None, value) nếu chưa đạt bậc nào."""
    value = get_metric_value(user, category)
    tier = category.tiers.filter(min_value__lte=value).order_by("-min_value").first()
    return tier, value


def get_all_earned_badges(user):
    """[(category, tier, value), ...] cho mọi category user đã đạt >= 1 bậc."""
    result = []
    for category in BadgeCategory.objects.filter(is_active=True):
        tier, value = get_earned_tier(user, category)
        if tier:
            result.append((category, tier, value))
    return result


def get_display_badge(user):
    """
    Danh hiệu hiển thị nổi bật (navbar/hồ sơ): ưu tiên danh hiệu user đã GHIM
    (display_order thấp nhất), fallback về danh hiệu nhóm "Đóng góp cộng
    đồng" nếu user chưa ghim gì. Trả (category, tier, value) hoặc (None, None, 0).
    """
    pinned = user.pinned_badges.select_related("category").order_by("display_order").first()
    if pinned:
        tier, value = get_earned_tier(user, pinned.category)
        if tier:
            return pinned.category, tier, value

    from apps.core.constants import CODE_TYPE_BADGE_CONTRIBUTION
    default_category = BadgeCategory.objects.filter(code_type=CODE_TYPE_BADGE_CONTRIBUTION).first()
    if default_category:
        tier, value = get_earned_tier(user, default_category)
        return default_category, tier, value

    return None, None, 0


def pin_badge(user, category):
    """
    Ghim 1 category để hiển thị. Raise ValueError (bắt ở view, hiện thông
    báo lỗi cho user) nếu: (1) chưa đạt bậc nào ở category đó, hoặc
    (2) đã ghim đủ MAX_PINNED_BADGES và category này chưa nằm trong đó.
    """
    from apps.core.properties import message

    tier, _ = get_earned_tier(user, category)
    if not tier:
        raise ValueError(message("badge.pin.error.not_earned", category_name=category.name))

    already_pinned = UserPinnedBadge.objects.filter(user=user, category=category).exists()
    if not already_pinned:
        current_count = UserPinnedBadge.objects.filter(user=user).count()
        if current_count >= MAX_PINNED_BADGES:
            raise ValueError(
                message("badge.pin.error.limit_reached", max_pinned=MAX_PINNED_BADGES)
            )

    next_order = UserPinnedBadge.objects.filter(user=user).count()
    obj, _created = UserPinnedBadge.objects.get_or_create(
        user=user, category=category, defaults={"display_order": next_order}
    )
    return obj


def unpin_badge(user, category):
    UserPinnedBadge.objects.filter(user=user, category=category).delete()


def award_points(user, action_code, points, contribution=None, note=""):
    """
    Cộng điểm cho user + ghi log UserPointTransaction + cập nhật
    User.total_points (denormalize, dùng F() để tránh race condition khi 2
    request cộng điểm cùng lúc). Gọi hàm này thay vì tự tạo
    UserPointTransaction thẳng, để total_points luôn nhất quán với log.
    """
    from django.contrib.auth import get_user_model
    from django.db import transaction
    from django.db.models import F
    from apps.gamification.models import UserPointTransaction

    # get_user_model() chứ KHÔNG phải type(user): gọi từ view thì `user` là
    # request.user, tức SimpleLazyObject bọc ngoài User — `type(user).objects`
    # nổ AttributeError. Lỗi này nằm im từ đầu vì trước SC11 chưa view nào cộng
    # điểm, chỉ có lệnh seed gọi tới.
    with transaction.atomic():
        UserPointTransaction.objects.create(
            user=user, action_code=action_code, points=points,
            contribution=contribution, note=note,
        )
        get_user_model().objects.filter(pk=user.pk).update(
            total_points=F("total_points") + points
        )
    user.refresh_from_db(fields=["total_points"])
    return user.total_points


# --------------------------------------------------------------------------
# Duyệt / từ chối góp ý (gọi từ view admin — hòm thư góp ý, SC12)
# --------------------------------------------------------------------------

CONTRIBUTION_TYPE_NEW_WORD = "001"
CONTRIBUTION_TYPE_EDIT_MEANING = "002"
CONTRIBUTION_TYPE_COMMENT = "003"

STATUS_PENDING = "001"
STATUS_APPROVED = "002"
STATUS_REJECTED = "003"

# action_code (PointRule / MasterCode code_type=CODE_TYPE_POINT_ACTION) ứng
# với mỗi loại góp ý ĐƯỢC DUYỆT — tra points thật từ bảng PointRule, không
# hardcode số điểm ở đây.
_APPROVAL_ACTION_CODE_BY_TYPE = {
    CONTRIBUTION_TYPE_NEW_WORD: "002",       # "Từ mới được duyệt"
    CONTRIBUTION_TYPE_EDIT_MEANING: "004",   # "Sửa nghĩa được duyệt"
    CONTRIBUTION_TYPE_COMMENT: "005",        # "Bình luận được duyệt"
}


# action_code ứng với việc GỬI góp ý (khác với DUYỆT ở dưới). Chỉ "Từ mới" và
# "Sửa nghĩa" được cộng điểm lúc gửi (+1, xem spec mục 4) — bình luận thì
# không, vì tần suất cao, cộng điểm lúc gửi là mời spam.
_SUBMIT_ACTION_CODE_BY_TYPE = {
    CONTRIBUTION_TYPE_NEW_WORD: "001",       # "Gửi góp ý từ mới"
    CONTRIBUTION_TYPE_EDIT_MEANING: "003",   # "Gửi sửa nghĩa/cách dùng"
}


def submit_contribution(user, contribution_type_code, **fields):
    """
    Tạo 1 góp ý ở trạng thái Chờ duyệt + cộng điểm GỬI nếu loại đó có.

    Mọi nơi tạo Contribution đều đi qua đây (màn SC11 lẫn ô bình luận nhanh ở
    flashcard) để điểm gửi không bị sót ở một đường và cộng hai lần ở đường
    kia. Số điểm tra từ PointRule, không hardcode.
    """
    from django.db import transaction

    from apps.gamification.models import Contribution, PointRule

    with transaction.atomic():
        contribution = Contribution.objects.create(
            user=user,
            contribution_type_code=contribution_type_code,
            status_code=STATUS_PENDING,
            **fields,
        )

        action_code = _SUBMIT_ACTION_CODE_BY_TYPE.get(contribution_type_code)
        if action_code:
            rule = PointRule.objects.filter(action_code=action_code).first()
            points = rule.points if rule else 0
            if points:
                award_points(
                    user, action_code, points, contribution=contribution,
                    note=f"Gửi góp ý #{contribution.pk}",
                )

    return contribution


def approve_contribution(contribution, reviewed_by, admin_response=""):
    """
    Duyệt 1 Contribution: áp dụng thay đổi vào Vocabulary (nếu là từ mới/sửa
    nghĩa), cộng điểm theo PointRule, cập nhật trạng thái + phản hồi.
    Bình luận (COMMENT) không đụng Vocabulary, chỉ đổi status để bắt đầu
    hiển thị công khai (xem Contribution model docstring).
    """
    from django.utils import timezone
    from django.db import transaction
    from apps.gamification.models import PointRule
    from apps.vocabulary.models import Vocabulary

    with transaction.atomic():
        if contribution.contribution_type_code == CONTRIBUTION_TYPE_NEW_WORD:
            vocab = Vocabulary.objects.create(
                word=contribution.proposed_word,
                reading=contribution.proposed_reading,
                meaning_vi=contribution.proposed_meaning_vi,
            )
            if contribution.proposed_topic_id:
                vocab.topics.add(contribution.proposed_topic_id)
            contribution.target_vocabulary = vocab

        elif contribution.contribution_type_code == CONTRIBUTION_TYPE_EDIT_MEANING:
            vocab = contribution.target_vocabulary
            if contribution.proposed_meaning_vi:
                vocab.meaning_vi = contribution.proposed_meaning_vi
            if contribution.proposed_reading:
                vocab.reading = contribution.proposed_reading
            vocab.save()

        action_code = _APPROVAL_ACTION_CODE_BY_TYPE.get(contribution.contribution_type_code)
        points = 0
        if action_code:
            rule = PointRule.objects.filter(action_code=action_code).first()
            points = rule.points if rule else 0

        contribution.status_code = STATUS_APPROVED
        contribution.reviewed_by = reviewed_by
        contribution.reviewed_at = timezone.now()
        contribution.admin_response = admin_response
        contribution.points_awarded = points
        contribution.save()

        if points:
            award_points(
                contribution.user, action_code, points,
                contribution=contribution, note=f"Góp ý #{contribution.pk} được duyệt",
            )

    return contribution


def reject_contribution(contribution, reviewed_by, admin_response):
    """Từ chối góp ý — bắt buộc admin_response (lý do), không cộng điểm."""
    from django.utils import timezone

    from apps.core.properties import message

    if not (admin_response or "").strip():
        raise ValueError(message("contribution.reject.error.reason_required"))

    contribution.status_code = STATUS_REJECTED
    contribution.reviewed_by = reviewed_by
    contribution.reviewed_at = timezone.now()
    contribution.admin_response = admin_response
    contribution.points_awarded = 0
    contribution.save()
    return contribution


# --------------------------------------------------------------------------
# SC13 — màn "Điểm & Thành tích"
# --------------------------------------------------------------------------
#
# Mọi số liệu của màn đó gom về đây, view chỉ lắp vào context. Lý do tách:
# ba khối (tiến độ từng nhóm danh hiệu / lịch sử điểm / bảng xếp hạng) đều là
# tính toán trên dữ liệu, không phải điều phối request — đúng ranh giới
# view-service mà project đang theo (xem apps/learning/services.py).

LEADERBOARD_SIZE = 10
POINT_HISTORY_SIZE = 10

# metric -> key ĐƠN VỊ trong label.properties ("điểm" / "từ" / "bài kiểm tra").
# KHÔNG viết "điểm" thẳng trong template: mỗi BadgeCategory đo một đại lượng
# khác nhau, câu "còn 282 điểm để lên Cố Vấn" chỉ đúng với nhóm Đóng góp; nhóm
# Học tập phải là "còn 282 từ".
_METRIC_UNIT_LABEL_KEY = {
    BadgeCategory.METRIC_CONTRIBUTION_POINTS: "badge.metric.unit.contribution_points",
    BadgeCategory.METRIC_WORDS_LEARNED: "badge.metric.unit.words_learned",
    BadgeCategory.METRIC_QUIZ_HIGH_SCORE_COUNT: "badge.metric.unit.quiz_high_score",
}


def metric_unit(category):
    """Đơn vị hiển thị của metric mà category này đo."""
    from apps.core.properties import label

    key = _METRIC_UNIT_LABEL_KEY.get(category.metric)
    return label(key, default="") if key else ""


def get_category_progress(user, category, pinned_code_types=()):
    """
    Toàn bộ số liệu để vẽ MỘT nhóm danh hiệu trên SC13: giá trị hiện tại, bậc
    đang đứng, bậc kế tiếp, % thanh tiến độ và trạng thái từng bậc.

    `pinned_code_types` truyền từ ngoài vào (một truy vấn cho cả trang) thay vì
    mỗi category lại hỏi DB "user có ghim nhóm này không".
    """
    tiers = list(category.tiers.order_by("min_value"))
    value = get_metric_value(user, category)

    earned = None
    next_tier = None
    for tier in tiers:
        if tier.min_value <= value:
            earned = tier
        elif next_tier is None:
            next_tier = tier

    # % đo TRONG KHOẢNG giữa bậc đang đứng và bậc kế tiếp, không phải
    # value/min_value của bậc cuối: nếu không thanh tiến độ sẽ gần như đứng im
    # ở các bậc đầu (ngưỡng bậc cuối lớn gấp hàng chục lần bậc đầu).
    floor_value = earned.min_value if earned else 0
    if next_tier:
        span = next_tier.min_value - floor_value
        percent = int(round((value - floor_value) * 100 / span)) if span > 0 else 100
    else:
        percent = 100  # đã ở bậc cao nhất
    percent = max(0, min(100, percent))

    tier_rows = [
        {
            "tier": tier,
            "name": category.tier_name(tier.code),
            "icon": tier.icon_emoji or category.icon_emoji,
            "min_value": tier.min_value,
            "is_earned": tier.min_value <= value,
            "is_current": earned is not None and tier.pk == earned.pk,
        }
        for tier in tiers
    ]

    return {
        "category": category,
        "unit": metric_unit(category),
        "value": value,
        "tiers": tier_rows,
        "tier_count": len(tier_rows),
        "earned_tier": earned,
        "earned_tier_name": category.tier_name(earned.code) if earned else "",
        "earned_tier_icon": (earned.icon_emoji or category.icon_emoji) if earned else category.icon_emoji,
        "next_tier": next_tier,
        "next_tier_name": category.tier_name(next_tier.code) if next_tier else "",
        "next_tier_min": next_tier.min_value if next_tier else None,
        "remaining": max(0, next_tier.min_value - value) if next_tier else 0,
        "percent": percent,
        "is_pinned": category.code_type in pinned_code_types,
    }


def get_all_category_progress(user):
    """Tiến độ của MỌI nhóm danh hiệu đang bật, theo thứ tự sort_order."""
    pinned = set(
        UserPinnedBadge.objects.filter(user=user).values_list("category__code_type", flat=True)
    )
    return [
        get_category_progress(user, category, pinned)
        for category in BadgeCategory.objects.filter(is_active=True).prefetch_related("tiers")
    ]


def get_highlight_progress(progress_list):
    """
    Nhóm được đưa lên khối lớn đầu trang SC13. Dùng ĐÚNG quy tắc của
    get_display_badge() (ưu tiên nhóm đã ghim, không có thì nhóm "Đóng góp
    cộng đồng") — hai chỗ lệch nhau thì hồ sơ và trang thành tích sẽ khoe hai
    danh hiệu khác nhau cho cùng một người.
    """
    from apps.core.constants import CODE_TYPE_BADGE_CONTRIBUTION

    for item in progress_list:
        if item["is_pinned"] and item["earned_tier"]:
            return item
    for item in progress_list:
        if item["category"].code_type == CODE_TYPE_BADGE_CONTRIBUTION:
            return item
    return progress_list[0] if progress_list else None


def get_point_history(user, limit=POINT_HISTORY_SIZE):
    """`limit` giao dịch điểm gần nhất (Meta.ordering đã là -created_at)."""
    from apps.gamification.models import UserPointTransaction

    return list(
        UserPointTransaction.objects.filter(user=user).select_related("contribution")[:limit]
    )


def get_contribution_stats(user):
    """Hai ô thống kê nhỏ trên SC13: góp ý được duyệt / bình luận được duyệt."""
    from apps.gamification.models import Contribution

    approved = Contribution.objects.filter(user=user, status_code=STATUS_APPROVED)
    return {
        "approved_total": approved.count(),
        "approved_comments": approved.filter(
            contribution_type_code=CONTRIBUTION_TYPE_COMMENT
        ).count(),
    }


def _contribution_category():
    from apps.core.constants import CODE_TYPE_BADGE_CONTRIBUTION

    return BadgeCategory.objects.filter(code_type=CODE_TYPE_BADGE_CONTRIBUTION).first()


def get_contribution_rank(user):
    """
    Hạng trên bảng xếp hạng điểm đóng góp (1 = cao nhất), None nếu chưa có
    điểm nào — chưa đóng góp thì không có hạng để khoe.

    Đồng điểm thì ĐỒNG HẠNG (đếm số người điểm cao hơn rồi +1), nên hai người
    cùng 218 điểm đều là hạng 8 chứ không phải 8 và 9.
    """
    from django.contrib.auth import get_user_model

    if not user.total_points:
        return None
    higher = (
        get_user_model()
        .objects.filter(is_active=True, total_points__gt=user.total_points)
        .count()
    )
    return higher + 1


def get_leaderboard(limit=LEADERBOARD_SIZE, current_user=None):
    """
    Top người đóng góp. Nếu `current_user` không nằm trong top, thêm DÒNG CỦA
    CHÍNH HỌ ở cuối (cờ `outside_top` để template chèn dòng "…") — bảng xếp
    hạng mà người xem không thấy mình ở đâu thì mất hết tác dụng thúc đẩy.

    Danh hiệu của từng dòng tính trong Python trên danh sách bậc đã nạp sẵn,
    không gọi get_earned_tier() cho từng user (N+1 truy vấn).
    """
    from django.contrib.auth import get_user_model

    category = _contribution_category()
    tiers_desc = list(category.tiers.order_by("-min_value")) if category else []

    def tier_for(points):
        for tier in tiers_desc:
            if tier.min_value <= points:
                return tier
        return None

    def build_row(rank, user, outside_top):
        tier = tier_for(user.total_points)
        return {
            "rank": rank,
            "user": user,
            "display_name": (user.first_name or "").strip() or user.get_username(),
            "points": user.total_points,
            "badge_name": category.tier_name(tier.code) if (tier and category) else "",
            "badge_icon": (tier.icon_emoji or category.icon_emoji) if tier else "",
            "is_me": current_user is not None and user.pk == current_user.pk,
            "outside_top": outside_top,
        }

    top = (
        get_user_model()
        .objects.filter(is_active=True, total_points__gt=0)
        .order_by("-total_points", "pk")[:limit]
    )
    rows = [build_row(i, user, False) for i, user in enumerate(top, start=1)]

    if current_user is not None and not any(row["is_me"] for row in rows):
        rank = get_contribution_rank(current_user)
        if rank:
            rows.append(build_row(rank, current_user, True))
    return rows
