"""
Test cho SC11 (Góp ý từ vựng) và SC12 (Hòm thư góp ý).

Chạy: python manage.py test apps.gamification
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.properties import message

from apps.gamification import services
from apps.gamification.models import Contribution, UserPointTransaction
from apps.vocabulary.models import Topic, Vocabulary

User = get_user_model()


class ContributionTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        call_command("seed_gamification", verbosity=0)

    def setUp(self):
        cache.clear()
        self.learner = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        self.staff = User.objects.create_user(
            username="quantri", password="MatKhauRatManh123", is_staff=True
        )
        self.topic = Topic.objects.create(name="Công việc", slug="cong-viec")
        self.word = Vocabulary.objects.create(
            word="注文する", reading="ちゅうもんする", meaning_vi="gọi món"
        )
        self.form_url = reverse("gamification:form")
        self.submit_url = reverse("gamification:submit")
        self.inbox_url = reverse("admin_panel:contribution_inbox")


class SubmitTests(ContributionTestCase):
    def test_login_required(self):
        self.assertRedirects(
            self.client.get(self.form_url), reverse("accounts:login") + "?next=" + self.form_url
        )

    def test_new_word_is_created_pending_and_awards_submit_point(self):
        self.client.force_login(self.learner)
        response = self.client.post(self.submit_url, {
            "type": "word",
            "word": "打ち合わせ",
            "reading": "うちあわせ",
            "meaning_vi": "buổi họp",
            "topic": self.topic.pk,
            "note": "Hay gặp trong email công việc",
        })
        self.assertRedirects(response, self.form_url + "?tab=mine")
        c = Contribution.objects.get()
        self.assertEqual(c.status_code, services.STATUS_PENDING)
        self.assertEqual(c.contribution_type_code, services.CONTRIBUTION_TYPE_NEW_WORD)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.total_points, 1)  # PointRule action 001
        self.assertEqual(UserPointTransaction.objects.filter(user=self.learner).count(), 1)

    def test_duplicate_word_is_rejected_at_the_form(self):
        """Từ đã có thì đây là góp ý 'Sửa nghĩa', không phải 'Từ mới'."""
        self.client.force_login(self.learner)
        response = self.client.post(self.submit_url, {
            "type": "word", "word": "注文する", "reading": "ちゅうもんする", "meaning_vi": "gọi món",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Contribution.objects.exists())

    def test_comment_does_not_award_submit_point(self):
        self.client.force_login(self.learner)
        self.client.post(self.submit_url, {
            "type": "comment",
            "target_vocabulary": self.word.pk,
            "comment_text": "Thường dùng ở nhà hàng.",
        })
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.total_points, 0)
        self.assertEqual(Contribution.objects.count(), 1)

    def test_invalid_type_falls_back_to_new_word_form(self):
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.form_url, {"type": "xxx"}).context["type_key"], "word")

    def test_link_from_flashcard_locks_the_word(self):
        """Vào từ màn học thì góp ý CHỈ cho đúng từ đó — ô chọn từ bị khoá."""
        from django import forms as django_forms

        self.client.force_login(self.learner)
        response = self.client.get(self.form_url, {"type": "meaning", "vocabulary": self.word.pk})

        self.assertEqual(response.context["locked_vocabulary"], self.word)
        field = response.context["form"].fields["target_vocabulary"]
        self.assertIsInstance(field.widget, django_forms.HiddenInput)
        self.assertEqual(list(field.queryset), [self.word])
        # Không còn <select> để đổi sang từ khác.
        self.assertNotContains(response, '<select name="target_vocabulary"')

    def test_open_from_menu_leaves_the_word_selectable(self):
        """Vào thẳng từ thanh menu thì ngược lại: ô chọn mở bình thường."""
        self.client.force_login(self.learner)
        response = self.client.get(self.form_url, {"type": "meaning"})
        self.assertIsNone(response.context["locked_vocabulary"])
        self.assertContains(response, '<select name="target_vocabulary"')

    def test_locked_form_refuses_a_different_word(self):
        """Sửa id trên DevTools cũng không góp ý sang từ khác được."""
        other = Vocabulary.objects.create(word="予約", reading="よやく", meaning_vi="đặt chỗ")
        self.client.force_login(self.learner)
        response = self.client.post(self.submit_url, {
            "type": "meaning",
            "locked_vocabulary": self.word.pk,     # đang khoá vào 注文する
            "target_vocabulary": other.pk,         # nhưng gửi lên 予約
            "proposed_meaning_vi": "đặt trước",
        })
        self.assertEqual(response.status_code, 200)  # render lại kèm lỗi
        self.assertFalse(Contribution.objects.exists())

    def test_locked_form_submits_the_locked_word(self):
        self.client.force_login(self.learner)
        self.client.post(self.submit_url, {
            "type": "meaning",
            "locked_vocabulary": self.word.pk,
            "target_vocabulary": self.word.pk,
            "proposed_meaning_vi": "đặt món, gọi món",
        })
        self.assertEqual(Contribution.objects.get().target_vocabulary, self.word)

    def test_type_links_carry_the_locked_word(self):
        """Bấm sang tab "Bình luận" không được làm mất từ đang khoá."""
        self.client.force_login(self.learner)
        response = self.client.get(self.form_url, {"type": "meaning", "vocabulary": self.word.pk})
        self.assertContains(response, f"?type=comment&vocabulary={self.word.pk}")

    def test_unknown_vocabulary_id_does_not_break_the_form(self):
        self.client.force_login(self.learner)
        response = self.client.get(self.form_url, {"type": "meaning", "vocabulary": 999999})
        self.assertEqual(response.status_code, 200)

    def test_mine_tab_shows_only_own_contributions(self):
        services.submit_contribution(
            self.learner, services.CONTRIBUTION_TYPE_COMMENT,
            target_vocabulary=self.word, comment_text="của tôi",
        )
        other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")
        services.submit_contribution(
            other, services.CONTRIBUTION_TYPE_COMMENT,
            target_vocabulary=self.word, comment_text="của người khác",
        )
        self.client.force_login(self.learner)
        response = self.client.get(self.form_url, {"tab": "mine"})
        self.assertEqual(len(response.context["page_obj"].object_list), 1)


class FlashcardCommentTests(ContributionTestCase):
    def test_quick_comment_box_goes_through_the_same_service(self):
        """Ô bình luận nhanh ở flashcard và màn SC11 phải ra cùng một kết quả."""
        self.client.force_login(self.learner)
        self.client.post(
            reverse("learning:flashcard_comment", args=[self.word.pk]),
            {"comment_text": "Ghi chú nhanh", "topic_slug": self.topic.slug},
        )
        c = Contribution.objects.get()
        self.assertEqual(c.contribution_type_code, services.CONTRIBUTION_TYPE_COMMENT)
        self.assertEqual(c.status_code, services.STATUS_PENDING)


class InboxTests(ContributionTestCase):
    def _pending(self, type_code=None, **kwargs):
        type_code = type_code or services.CONTRIBUTION_TYPE_NEW_WORD
        defaults = {
            "proposed_word": "打ち合わせ",
            "proposed_reading": "うちあわせ",
            "proposed_meaning_vi": "buổi họp",
            "proposed_topic": self.topic,
        }
        defaults.update(kwargs)
        return services.submit_contribution(self.learner, type_code, **defaults)

    def test_learner_gets_403(self):
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.inbox_url).status_code, 403)

    def test_default_filter_is_pending(self):
        pending = self._pending()
        self.client.force_login(self.staff)
        response = self.client.get(self.inbox_url)
        self.assertEqual([c.pk for c in response.context["contributions"]], [pending.pk])

    def test_approving_a_new_word_creates_the_vocabulary_and_awards_points(self):
        c = self._pending()
        self.client.force_login(self.staff)
        self.client.post(reverse("admin_panel:contribution_action", args=[c.pk]), {
            "action": "approve", "status": "pending",
            "word": "打ち合わせ", "reading": "うちあわせ", "meaning_vi": "buổi họp",
            "topic": self.topic.pk, "admin_response": "Cảm ơn bạn!",
        })
        c.refresh_from_db()
        self.assertEqual(c.status_code, services.STATUS_APPROVED)
        self.assertTrue(Vocabulary.objects.filter(word="打ち合わせ").exists())
        self.assertEqual(c.points_awarded, 10)  # PointRule action 002
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.total_points, 11)  # 1 khi gửi + 10 khi duyệt

    def test_admin_can_edit_the_proposal_before_approving(self):
        c = self._pending()
        self.client.force_login(self.staff)
        self.client.post(reverse("admin_panel:contribution_action", args=[c.pk]), {
            "action": "approve", "status": "pending",
            "word": "打合せ", "reading": "うちあわせ", "meaning_vi": "buổi họp (viết gọn)",
        })
        self.assertTrue(Vocabulary.objects.filter(word="打合せ").exists())
        self.assertFalse(Vocabulary.objects.filter(word="打ち合わせ").exists())

    def test_approving_an_edit_updates_the_target_word(self):
        c = self._pending(
            services.CONTRIBUTION_TYPE_EDIT_MEANING,
            proposed_word="", proposed_reading="", proposed_topic=None,
            target_vocabulary=self.word, proposed_meaning_vi="đặt món, gọi món",
        )
        self.client.force_login(self.staff)
        self.client.post(reverse("admin_panel:contribution_action", args=[c.pk]), {
            "action": "approve", "status": "pending", "meaning_vi": "đặt món, gọi món",
        })
        self.word.refresh_from_db()
        self.assertEqual(self.word.meaning_vi, "đặt món, gọi món")

    def test_approved_comment_becomes_visible_on_flashcard(self):
        c = self._pending(
            services.CONTRIBUTION_TYPE_COMMENT,
            proposed_word="", proposed_reading="", proposed_meaning_vi="", proposed_topic=None,
            target_vocabulary=self.word, comment_text="Dùng khi gọi món ở nhà hàng.",
        )
        services.approve_contribution(c, self.staff)
        visible = Contribution.objects.filter(
            target_vocabulary=self.word,
            contribution_type_code=services.CONTRIBUTION_TYPE_COMMENT,
            status_code=services.STATUS_APPROVED,
        )
        self.assertEqual(visible.count(), 1)

    def test_reject_without_reason_keeps_status_pending(self):
        c = self._pending()
        self.client.force_login(self.staff)
        self.client.post(reverse("admin_panel:contribution_action", args=[c.pk]), {
            "action": "reject", "status": "pending", "admin_response": "   ",
        })
        c.refresh_from_db()
        self.assertEqual(c.status_code, services.STATUS_PENDING)

    def test_reject_without_reason_says_so_right_at_the_field(self):
        """Lỗi thật 19/09/2026: admin bấm "Từ chối" mà chưa ghi lý do thì tưởng
        trang không xử lý gì. Nút nằm cuối một trang dài, còn báo lỗi thì chỉ có
        một dòng nhạt ở đầu trang. Giờ redirect phải mang theo neo #chi-tiet +
        mã lỗi để khối chi tiết hiện lỗi ngay dưới ô nhập."""
        c = self._pending()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_panel:contribution_action", args=[c.pk]),
            {"action": "reject", "status": "pending"},
        )
        self.assertIn("error=reason_required", response["Location"])
        self.assertTrue(response["Location"].endswith("#chi-tiet"))

        page = self.client.get(response["Location"].split("#")[0])
        html = page.content.decode()
        self.assertIn('id="chi-tiet"', html)
        self.assertIn('aria-invalid="true"', html)
        # Lỗi hiện HAI chỗ: flash đầu trang và ngay cạnh ô nhập.
        text = message("contribution.reject.error.reason_required")
        self.assertIn(f'<p class="error">{text}</p>', html)
        self.assertIn(f'<div class="flash error" role="alert">{text}</div>', html)

    def test_junk_error_param_does_not_render_anything(self):
        """`?error=` là do người dùng gõ được — chỉ mã đã khai báo mới hiện."""
        self._pending()
        self.client.force_login(self.staff)
        html = self.client.get(
            reverse("admin_panel:contribution_inbox") + "?status=pending&error=linh-tinh"
        ).content.decode()
        self.assertNotIn('<p class="error">', html)

    def test_reject_button_carries_the_browser_side_check(self):
        """main.js bắt ô trống ngay trên trình duyệt; tắt JS thì view vẫn chặn."""
        self._pending()
        self.client.force_login(self.staff)
        html = self.client.get(reverse("admin_panel:contribution_inbox")).content.decode()
        self.assertIn('data-reject-requires="id_admin_response"', html)

    def test_reject_with_reason_awards_nothing(self):
        c = self._pending()
        self.client.force_login(self.staff)
        self.client.post(reverse("admin_panel:contribution_action", args=[c.pk]), {
            "action": "reject", "status": "pending", "admin_response": "Từ này đã có rồi.",
        })
        c.refresh_from_db()
        self.assertEqual(c.status_code, services.STATUS_REJECTED)
        self.assertEqual(c.points_awarded, 0)
        self.learner.refresh_from_db()
        self.assertEqual(self.learner.total_points, 1)  # chỉ còn điểm lúc gửi

    def test_cannot_review_twice(self):
        c = self._pending()
        self.client.force_login(self.staff)
        url = reverse("admin_panel:contribution_action", args=[c.pk])
        self.client.post(url, {"action": "approve", "status": "pending",
                               "word": "打ち合わせ", "reading": "うちあわせ", "meaning_vi": "buổi họp"})
        self.client.post(url, {"action": "reject", "status": "pending", "admin_response": "đổi ý"})
        c.refresh_from_db()
        self.assertEqual(c.status_code, services.STATUS_APPROVED)

    def test_sidebar_link_is_live(self):
        """Trước 16/09/2026 mục này trỏ sang /admin/ của Django."""
        self.client.force_login(self.staff)
        html = self.client.get(reverse("admin_panel:overview")).content.decode()
        self.assertIn(self.inbox_url, html)


class BadgeTests(ContributionTestCase):
    def test_points_from_approval_raise_the_contribution_badge_tier(self):
        """Đủ điểm thì bậc danh hiệu nhóm 'Đóng góp cộng đồng' lên theo."""
        from apps.core.constants import CODE_TYPE_BADGE_CONTRIBUTION
        from apps.gamification.models import BadgeCategory

        category = BadgeCategory.objects.get(code_type=CODE_TYPE_BADGE_CONTRIBUTION)
        before, _ = services.get_earned_tier(self.learner, category)

        services.award_points(self.learner, "002", 60, note="test")
        self.learner.refresh_from_db()
        after, value = services.get_earned_tier(self.learner, category)

        self.assertEqual(value, 60)
        self.assertNotEqual(after.pk, before.pk if before else None)
