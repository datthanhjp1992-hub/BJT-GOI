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
    tier, _ = get_earned_tier(user, category)
    if not tier:
        raise ValueError(f"Bạn chưa đạt danh hiệu nào ở nhóm '{category.name}', chưa thể ghim.")

    already_pinned = UserPinnedBadge.objects.filter(user=user, category=category).exists()
    if not already_pinned:
        current_count = UserPinnedBadge.objects.filter(user=user).count()
        if current_count >= MAX_PINNED_BADGES:
            raise ValueError(f"Chỉ được ghim tối đa {MAX_PINNED_BADGES} danh hiệu — bỏ ghim bớt trước khi thêm.")

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
    from django.db import transaction
    from django.db.models import F
    from apps.gamification.models import UserPointTransaction

    with transaction.atomic():
        UserPointTransaction.objects.create(
            user=user, action_code=action_code, points=points,
            contribution=contribution, note=note,
        )
        type(user).objects.filter(pk=user.pk).update(total_points=F("total_points") + points)
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
                bjt_level=contribution.proposed_bjt_level or "J5",
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
            if contribution.proposed_bjt_level:
                vocab.bjt_level = contribution.proposed_bjt_level
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

    if not admin_response:
        raise ValueError("Cần nhập lý do từ chối để phản hồi cho người gửi.")

    contribution.status_code = STATUS_REJECTED
    contribution.reviewed_by = reviewed_by
    contribution.reviewed_at = timezone.now()
    contribution.admin_response = admin_response
    contribution.points_awarded = 0
    contribution.save()
    return contribution
