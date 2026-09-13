"""
Test cho SC07_QuanTriAdmin.

Chạy: python manage.py test apps.admin_panel
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core import dataio
from apps.core.properties import label
from apps.gamification.models import Contribution
from apps.vocabulary.models import ExampleSentence, Topic, Vocabulary

from .views import CONTRIBUTION_STATUS_PENDING

User = get_user_model()


class AdminPanelTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.url = reverse("admin_panel:overview")
        self.staff = User.objects.create_user(
            username="quantri", password="MatKhauRatManh123", is_staff=True,
            first_name="Nguyễn Thành Đạt",
        )
        self.learner = User.objects.create_user(
            username="nguoihoc", password="MatKhauRatManh123",
        )


class AccessTests(AdminPanelTestCase):
    def test_anonymous_is_sent_to_login(self):
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:login") + "?next=" + self.url
        )

    def test_normal_user_gets_403_not_a_redirect(self):
        """403 chứ không redirect: bị đá về trang đăng nhập khi đang đăng nhập
        khiến người dùng tưởng mình vừa bị đăng xuất."""
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_staff_can_open(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_panel/overview.html")


class OverviewContentTests(AdminPanelTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def test_stats_are_real_numbers(self):
        topic = Topic.objects.create(name="Nhà hàng", slug="nha-hang")
        vocab = Vocabulary.objects.create(
            word="予約", reading="よやく", meaning_vi="đặt chỗ", bjt_level="J4",
        )
        Contribution.objects.create(
            user=self.learner, contribution_type_code="001",
            status_code=CONTRIBUTION_STATUS_PENDING, target_vocabulary=vocab,
        )
        Contribution.objects.create(
            user=self.learner, contribution_type_code="001",
            status_code="002",  # đã duyệt -> không được đếm
            target_vocabulary=vocab,
        )
        # Tài khoản bị khoá không tính vào "người dùng hoạt động".
        User.objects.create_user(username="bikhoa", password="x", is_active=False)

        stats = self.client.get(self.url).context["stats"]
        self.assertEqual(stats["active_users"], 2)          # staff + learner
        self.assertEqual(stats["total_vocabulary"], 1)
        self.assertEqual(stats["total_topics"], 1)
        self.assertEqual(stats["pending_contributions"], 1)
        self.assertEqual(topic.slug, "nha-hang")

    def test_recent_users_are_newest_first_and_capped(self):
        from .views import RECENT_USER_LIMIT

        for i in range(RECENT_USER_LIMIT + 3):
            User.objects.create_user(username="hv%02d" % i, password="x")
        rows = self.client.get(self.url).context["recent_users"]
        self.assertEqual(len(rows), RECENT_USER_LIMIT)
        usernames = [u.get_username() for u in rows]
        self.assertEqual(usernames, sorted(usernames, reverse=True))

    def test_sidebar_links_to_django_admin(self):
        """Sửa/xoá TỪNG bản ghi vẫn là việc của Django admin.

        SC07b chỉ nhận phần nhập hàng loạt từ file (thứ Django admin không có).
        Nếu ai đó gỡ các link này để viết lại form CRUD từng bảng, test đỏ.
        """
        response = self.client.get(self.url)
        for url_name in (
            "admin:accounts_user_changelist",
            "admin:vocabulary_vocabulary_changelist",
            "admin:vocabulary_topic_changelist",
            "admin:gamification_contribution_changelist",
        ):
            self.assertContains(response, reverse(url_name))

    def test_greeting_uses_full_name(self):
        self.assertContains(self.client.get(self.url), "Nguyễn Thành Đạt")


class TopbarLinkTests(AdminPanelTestCase):
    def test_link_visible_for_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("learning:dashboard"))
        self.assertContains(response, reverse("admin_panel:overview"))
        self.assertContains(response, label("common.nav.admin"))

    def test_link_hidden_for_normal_user(self):
        self.client.force_login(self.learner)
        response = self.client.get(reverse("learning:dashboard"))
        self.assertNotContains(response, reverse("admin_panel:overview"))


# ---------------------------------------------------------------------------
# SC07b — nhập / xuất dữ liệu bằng CSV & Excel
# ---------------------------------------------------------------------------

def csv_upload(name, header, *rows):
    """Dựng 1 file CSV trong bộ nhớ, đúng kiểu trình duyệt gửi lên."""
    lines = [",".join(header)]
    lines += [",".join(str(c) for c in row) for row in rows]
    body = "\r\n".join(lines).encode("utf-8-sig")
    return SimpleUploadedFile(name, body, content_type="text/csv")


class DataIoEngineTests(TestCase):
    """Phần thuần logic của apps/core/dataio.py."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def test_registry_covers_exactly_the_18_local_tables(self):
        models = dataio.importable_models()
        self.assertEqual(len(models), 18, [dataio.model_label(m) for m in models])
        labels = {dataio.model_label(m) for m in models}
        self.assertIn("vocabulary.vocabulary", labels)
        self.assertIn("vocabulary.vocabularytopic", labels)
        # Bảng của django.contrib.auth KHÔNG nằm trong danh sách.
        self.assertNotIn("auth.group", labels)
        self.assertNotIn("auth.permission", labels)

    def test_dependencies_come_before_dependents(self):
        order = [dataio.model_label(m) for m in dataio.importable_models()]
        self.assertLess(order.index("vocabulary.topic"), order.index("vocabulary.vocabularytopic"))
        self.assertLess(order.index("vocabulary.vocabulary"), order.index("vocabulary.examplesentence"))

    def test_columns_drop_pk_and_audit_columns(self):
        headers = dataio.headers_for(Topic)
        self.assertEqual(headers, ["name", "slug", "icon_emoji", "description"])
        for banned in ("id", "created_at", "created_by", "updated_at", "updated_by"):
            self.assertNotIn(banned, headers)

    def test_foreign_key_becomes_natural_key_columns(self):
        """FK dò theo khoá tự nhiên chứ không bắt admin gõ id thô."""
        self.assertEqual(
            dataio.headers_for(ExampleSentence),
            ["vocabulary__word", "vocabulary__reading", "sentence_jp", "sentence_vi"],
        )

    def test_m2m_has_no_column_but_is_reported(self):
        headers = dataio.headers_for(Vocabulary)
        self.assertNotIn("topics", headers)
        self.assertEqual(
            dataio.skipped_m2m_names(Vocabulary), [("topics", "vocabulary.vocabularytopic")]
        )

    def test_every_declared_natural_key_names_real_fields(self):
        """Gõ sai tên field trong NATURAL_KEYS thì câu dò trùng sẽ nổ FieldError
        ngay giữa lúc admin đang nhập — bắt ở đây thay vì ở production."""
        for label_, keys in dataio.NATURAL_KEYS.items():
            model = dataio.get_importable_model(label_)
            self.assertIsNotNone(model, label_)
            for name in keys:
                model._meta.get_field(name)  # raise FieldDoesNotExist nếu sai
            self.assertEqual(dataio.duplicate_fields(model), tuple(keys), label_)

    def test_duplicate_key_falls_back_to_unique_constraint(self):
        self.assertEqual(dataio.duplicate_fields(Vocabulary), ("word", "reading"))
        self.assertEqual(dataio.duplicate_fields(ExampleSentence), ())

    def test_xlsx_round_trip_keeps_headers(self):
        payload = dataio.write_xlsx(["a", "b"], [["1", "2"]], guide_rows=[["Cột"]], sheet_title="t")
        headers, rows = dataio.read_table(payload, "x.xlsx")
        self.assertEqual(headers, ["a", "b"])
        self.assertEqual(rows, [["1", "2"]])

    def test_too_many_rows_is_refused(self):
        rows = [["x"]] * (dataio.MAX_IMPORT_ROWS + 1)
        payload = dataio.write_csv(["name"], rows)
        with self.assertRaises(dataio.DataFileError) as ctx:
            dataio.read_table(payload, "x.csv")
        self.assertEqual(ctx.exception.message_key, "admin.data.error.too_many_rows")


class DataImportViewTests(AdminPanelTestCase):
    def setUp(self):
        super().setUp()
        # staff thường KHÔNG tự động có quyền thêm vào mọi bảng.
        self.admin = User.objects.create_superuser(
            username="sieuquantri", password="MatKhauRatManh123", email="a@b.c",
        )
        self.index_url = reverse("admin_panel:data_index")
        self.topic_import_url = reverse("admin_panel:data_import", args=["vocabulary.topic"])

    # -- quyền --------------------------------------------------------------
    def test_learner_cannot_open_data_screen(self):
        self.client.force_login(self.learner)
        self.assertEqual(self.client.get(self.index_url).status_code, 403)

    def test_staff_without_add_permission_cannot_import(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.index_url).status_code, 200)
        self.assertEqual(self.client.get(self.topic_import_url).status_code, 403)

    def test_unknown_table_is_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(
            self.client.get(reverse("admin_panel:data_import", args=["auth.group"])).status_code,
            404,
        )

    # -- tải mẫu & xuất -----------------------------------------------------
    def test_csv_template_has_header_row_only(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_panel:data_template", args=["vocabulary.topic", "csv"])
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8-sig").strip()
        self.assertEqual(body, "name,slug,icon_emoji,description")

    def test_xlsx_export_returns_current_rows(self):
        Topic.objects.create(name="Nhà hàng", slug="nha-hang")
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_panel:data_export", args=["vocabulary.topic", "xlsx"])
        )
        self.assertEqual(response.status_code, 200)
        headers, rows = dataio.read_table(response.content, "x.xlsx")
        self.assertEqual(headers, ["name", "slug", "icon_emoji", "description"])
        self.assertEqual([r[1] for r in rows], ["nha-hang"])

    # -- xem trước ----------------------------------------------------------
    def test_preview_classifies_rows_and_writes_nothing(self):
        Topic.objects.create(name="Nhà hàng", slug="nha-hang")
        self.client.force_login(self.admin)
        upload = csv_upload(
            "topics.csv",
            ["name", "slug", "icon_emoji", "description"],
            ["Sân bay", "san-bay", "", ""],          # mới
            ["Nhà hàng", "nha-hang", "", ""],        # trùng slug -> bỏ qua
            ["", "thieu-ten", "", ""],               # thiếu name -> lỗi
        )
        response = self.client.post(self.topic_import_url, {"data_file": upload})
        report = response.context["report"]
        self.assertEqual((report.new_count, report.duplicate_count, report.error_count), (1, 1, 1))
        self.assertFalse(report.can_apply)  # còn dòng lỗi thì không cho ghi
        self.assertEqual(Topic.objects.count(), 1)  # chưa ghi gì

    def test_missing_required_column_is_reported(self):
        self.client.force_login(self.admin)
        upload = csv_upload("topics.csv", ["slug"], ["chi-co-slug"])
        response = self.client.post(self.topic_import_url, {"data_file": upload})
        self.assertEqual(response.context["report"].missing_columns, ["name"])

    def test_unsupported_extension_is_refused(self):
        self.client.force_login(self.admin)
        upload = SimpleUploadedFile("data.txt", b"name\nX", content_type="text/plain")
        response = self.client.post(self.topic_import_url, {"data_file": upload})
        self.assertIsNone(response.context.get("report"))
        self.assertContains(response, "csv")

    # -- ghi thật -----------------------------------------------------------
    def _preview(self, url, upload):
        response = self.client.post(url, {"data_file": upload})
        return response.context["report"], response.context["token"]

    def test_confirm_inserts_new_rows_and_skips_duplicates(self):
        Topic.objects.create(name="Nhà hàng", slug="nha-hang")
        self.client.force_login(self.admin)
        report, token = self._preview(
            self.topic_import_url,
            csv_upload(
                "topics.csv",
                ["name", "slug", "icon_emoji", "description"],
                ["Sân bay", "san-bay", "", ""],
                ["Nhà hàng", "nha-hang", "", ""],
            ),
        )
        self.assertTrue(report.can_apply)
        self.assertTrue(token)
        response = self.client.post(
            reverse("admin_panel:data_import_confirm", args=["vocabulary.topic"]),
            {"token": token},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Topic.objects.count(), 2)
        self.assertTrue(Topic.objects.filter(slug="san-bay").exists())

    def test_created_by_is_filled_from_the_logged_in_admin(self):
        """bulk_create bỏ qua save() nên KHÔNG dùng — audit phải còn nguyên."""
        self.client.force_login(self.admin)
        report, token = self._preview(
            self.topic_import_url,
            csv_upload("t.csv", ["name", "slug", "icon_emoji", "description"], ["Sân bay", "san-bay", "", ""]),
        )
        self.client.post(
            reverse("admin_panel:data_import_confirm", args=["vocabulary.topic"]),
            {"token": token},
        )
        topic = Topic.objects.get(slug="san-bay")
        self.assertEqual(topic.created_by, self.admin)
        self.assertEqual(topic.updated_by, self.admin)

    def test_confirm_without_a_preview_token_writes_nothing(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse("admin_panel:data_import_confirm", args=["vocabulary.topic"]),
            {"token": "khong-co-that"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Topic.objects.count(), 0)

    def test_confirm_only_accepts_post(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_panel:data_import_confirm", args=["vocabulary.topic"])
        )
        self.assertEqual(response.status_code, 405)

    # -- khoá ngoại theo khoá tự nhiên --------------------------------------
    def test_foreign_key_is_resolved_by_natural_key(self):
        vocab = Vocabulary.objects.create(
            word="予約", reading="よやく", meaning_vi="đặt chỗ", bjt_level="J4",
        )
        self.client.force_login(self.admin)
        url = reverse("admin_panel:data_import", args=["vocabulary.examplesentence"])
        report, token = self._preview(
            url,
            csv_upload(
                "vd.csv",
                ["vocabulary__word", "vocabulary__reading", "sentence_jp", "sentence_vi"],
                ["予約", "よやく", "予約をお願いします。", "Cho tôi đặt chỗ."],
            ),
        )
        self.assertTrue(report.can_apply)
        self.client.post(
            reverse("admin_panel:data_import_confirm", args=["vocabulary.examplesentence"]),
            {"token": token},
        )
        self.assertEqual(ExampleSentence.objects.get().vocabulary, vocab)

    def test_unknown_foreign_key_becomes_a_row_error(self):
        self.client.force_login(self.admin)
        url = reverse("admin_panel:data_import", args=["vocabulary.examplesentence"])
        report, _ = self._preview(
            url,
            csv_upload(
                "vd.csv",
                ["vocabulary__word", "vocabulary__reading", "sentence_jp", "sentence_vi"],
                ["không-có", "なし", "A", "B"],
            ),
        )
        self.assertEqual(report.error_count, 1)
        self.assertIn("vocabulary", report.problem_rows[0].errors[0])
        self.assertEqual(ExampleSentence.objects.count(), 0)

    # -- mật khẩu -----------------------------------------------------------
    def test_imported_user_never_stores_a_raw_password(self):
        self.client.force_login(self.admin)
        url = reverse("admin_panel:data_import", args=["accounts.user"])
        response = self.client.post(
            url,
            {
                "data_file": csv_upload(
                    "u.csv",
                    dataio.headers_for(User),
                    [
                        "MatKhauRatManh123" if h == "password"
                        else ("hocvienmoi" if h == "username" else "")
                        for h in dataio.headers_for(User)
                    ],
                )
            },
        )
        report = response.context["report"]
        self.assertTrue(report.can_apply, [r.errors for r in report.problem_rows])
        self.client.post(
            reverse("admin_panel:data_import_confirm", args=["accounts.user"]),
            {"token": response.context["token"]},
        )
        imported = User.objects.get(username="hocvienmoi")
        self.assertNotEqual(imported.password, "MatKhauRatManh123")
        self.assertTrue(imported.check_password("MatKhauRatManh123"))


    # -- rò rỉ cú pháp template ---------------------------------------------
    def test_import_screen_renders_without_template_leaks(self):
        """TemplateLeakTests ở apps.core chỉ chạy được với tài khoản staff
        thường, mà màn nhập đòi quyền add nên phải kiểm ở đây."""
        from apps.core.tests import TEMPLATE_MARKERS

        self.client.force_login(self.admin)
        report_html = self.client.post(
            self.topic_import_url,
            {"data_file": csv_upload("t.csv", ["name", "slug", "icon_emoji", "description"], ["Sân bay", "san-bay", "", ""])},
        ).content.decode()
        for marker in TEMPLATE_MARKERS:
            self.assertNotIn(marker, report_html, msg=f'màn nhập còn sót "{marker}"')


class DataSidebarTests(AdminPanelTestCase):
    def test_overview_links_to_the_data_screen(self):
        self.client.force_login(self.staff)
        self.assertContains(
            self.client.get(reverse("admin_panel:overview")),
            reverse("admin_panel:data_index"),
        )
