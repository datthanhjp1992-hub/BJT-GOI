"""
Test cho SC14 — Báo cáo lỗi.

Chạy: python manage.py test apps.error_reports
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.constants import (
    ERROR_STATUS_DISMISSED,
    ERROR_STATUS_FIXED,
    ERROR_STATUS_PENDING,
)
from apps.error_reports import services
from apps.error_reports.models import ErrorReport
from apps.vocabulary.models import Topic, Vocabulary

User = get_user_model()


class ErrorReportTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.learner = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        self.staff = User.objects.create_user(
            username="quantri", password="MatKhauRatManh123", is_staff=True
        )
        self.topic = Topic.objects.create(name="Công việc", slug="cong-viec")
        self.word = Vocabulary.objects.create(
            word="見積もり", reading="みつもり", meaning_vi="báo giá"
        )

    def _report(self, **kwargs):
        defaults = {
            "user": self.learner,
            "vocabulary": self.word,
            "error_type_code": "001",
            "description": "Nghĩa tiếng Việt đang ghi sai, đúng phải là 'bản dự toán'.",
        }
        defaults.update(kwargs)
        return ErrorReport.objects.create(**defaults)


class CreateTests(ErrorReportTestCase):
    def test_login_required(self):
        url = reverse("error_reports:create")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_submit_creates_pending_report_linked_to_word(self):
        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("error_reports:create"),
            {
                "vocabulary": self.word.pk,
                "error_type_code": "001",
                "description": "Nghĩa tiếng Việt sai, đúng phải là 'bản dự toán'.",
                "suggested_fix": "bản dự toán",
            },
        )
        self.assertRedirects(response, reverse("error_reports:mine"))
        report = ErrorReport.objects.get()
        self.assertEqual(report.user, self.learner)
        self.assertEqual(report.vocabulary, self.word)
        self.assertEqual(report.status_code, ERROR_STATUS_PENDING)

    def test_description_too_short_is_rejected(self):
        self.client.force_login(self.learner)
        response = self.client.post(
            reverse("error_reports:create"),
            {"vocabulary": self.word.pk, "error_type_code": "001", "description": "sai"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ErrorReport.objects.exists())

    def test_unknown_vocabulary_id_still_submits_as_general_report(self):
        """Id rác trên query string không được làm vỡ form — báo lỗi chung vẫn
        gửi được, chỉ là không gắn với từ nào."""
        self.client.force_login(self.learner)
        self.client.post(
            reverse("error_reports:create"),
            {
                "vocabulary": 999999,
                "error_type_code": "006",
                "description": "Trang danh sách từ vựng bị vỡ bố cục trên điện thoại.",
            },
        )
        self.assertIsNone(ErrorReport.objects.get().vocabulary)

    def test_mine_shows_only_own_reports(self):
        self._report()
        other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")
        self._report(user=other)
        self.client.force_login(self.learner)
        response = self.client.get(reverse("error_reports:mine"))
        self.assertEqual(len(response.context["page_obj"].object_list), 1)


class ServiceTests(ErrorReportTestCase):
    def test_mark_fixed_records_handler(self):
        report = services.mark_fixed(self._report(), self.staff, "Đã sửa lại nghĩa.")
        self.assertEqual(report.status_code, ERROR_STATUS_FIXED)
        self.assertEqual(report.handled_by, self.staff)
        self.assertIsNotNone(report.handled_at)

    def test_dismiss_requires_a_reason(self):
        with self.assertRaises(services.ErrorReportActionError):
            services.dismiss(self._report(), self.staff, "   ")

    def test_cannot_handle_twice(self):
        report = self._report()
        services.mark_fixed(report, self.staff)
        with self.assertRaises(services.ErrorReportActionError):
            services.dismiss(report, self.staff, "trùng")

    def test_reopen_clears_handler(self):
        report = self._report()
        services.mark_fixed(report, self.staff)
        services.reopen(report, self.staff)
        self.assertEqual(report.status_code, ERROR_STATUS_PENDING)
        self.assertIsNone(report.handled_by)


class AdminScreenTests(ErrorReportTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("admin_panel:error_report_list")

    def test_learner_gets_403(self):
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_default_filter_is_pending(self):
        pending = self._report()
        fixed = self._report()
        services.mark_fixed(fixed, self.staff)
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual([r.pk for r in response.context["reports"]], [pending.pk])
        self.assertEqual(response.context["selected"].pk, pending.pk)

    def test_filter_all_shows_everything(self):
        self._report()
        services.mark_fixed(self._report(), self.staff)
        self.client.force_login(self.staff)
        response = self.client.get(self.url, {"status": "all"})
        self.assertEqual(len(response.context["reports"]), 2)

    def test_unknown_filter_falls_back_to_pending(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url, {"status": "xxx"}).context["status_key"], "pending")

    def test_fix_action_updates_record_and_redirects_back(self):
        report = self._report()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("admin_panel:error_report_action", args=[report.pk]),
            {"action": "fix", "admin_response": "Đã sửa.", "status": "pending"},
        )
        report.refresh_from_db()
        self.assertEqual(report.status_code, ERROR_STATUS_FIXED)
        self.assertIn(f"selected={report.pk}", response["Location"])

    def test_dismiss_without_reason_keeps_status(self):
        report = self._report()
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_panel:error_report_action", args=[report.pk]),
            {"action": "dismiss", "admin_response": "", "status": "pending"},
        )
        report.refresh_from_db()
        self.assertEqual(report.status_code, ERROR_STATUS_PENDING)

    def test_dismiss_with_reason_works(self):
        report = self._report()
        self.client.force_login(self.staff)
        self.client.post(
            reverse("admin_panel:error_report_action", args=[report.pk]),
            {"action": "dismiss", "admin_response": "Trùng với báo lỗi #1.", "status": "pending"},
        )
        report.refresh_from_db()
        self.assertEqual(report.status_code, ERROR_STATUS_DISMISSED)

    def test_overview_counts_unresolved_reports(self):
        self._report()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("admin_panel:overview"))
        self.assertEqual(response.context["stats"]["unresolved_reports"], 1)

    def test_sidebar_link_is_live_on_every_admin_screen(self):
        """Trước khi có màn này, "Báo cáo lỗi" là link chết href="#"."""
        self.client.force_login(self.staff)
        html = self.client.get(reverse("admin_panel:overview")).content.decode()
        self.assertIn(self.url, html)


class MasterCodeTests(ErrorReportTestCase):
    def test_names_come_from_mastercode_not_hardcode(self):
        report = self._report(error_type_code="002")
        self.assertEqual(report.error_type_name, "Sai cách đọc / furigana")
        self.assertEqual(report.status_name, "Chờ xử lý")

    def test_status_choices_hide_the_parent_code(self):
        from apps.core.constants import ERROR_STATUS_HANDLED_PARENT, error_status_choices

        codes = [code for code, _ in error_status_choices()]
        self.assertNotIn(ERROR_STATUS_HANDLED_PARENT, codes)
