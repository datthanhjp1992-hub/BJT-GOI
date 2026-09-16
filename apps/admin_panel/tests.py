"""
Test cho SC07_QuanTriAdmin.

Chạy: python manage.py test apps.admin_panel
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core import dataio
from apps.core.properties import label
from apps.gamification.models import Contribution, UserPinnedBadge
from apps.learning.models import UserWordlist, UserWordlistWord
from apps.practice_sheets.models import PracticeSheetWord
from apps.vocabulary.models import ExampleSentence, Topic, Vocabulary, VocabularyTopic

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
            word="予約", reading="よやく", meaning_vi="đặt chỗ",
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
        ):
            self.assertContains(response, reverse(url_name))

    def test_sidebar_links_to_the_real_inbox_not_django_admin(self):
        """Từ 16/09/2026 "Hòm thư góp ý" là màn tự viết (SC12), không còn đẩy
        sang /admin/gamification/contribution/ nữa."""
        response = self.client.get(self.url)
        self.assertContains(response, reverse("admin_panel:contribution_inbox"))
        self.assertNotContains(response, reverse("admin:gamification_contribution_changelist"))

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
        self.assertEqual(len(models), 19, [dataio.model_label(m) for m in models])
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
        self.assertEqual(headers, ["name", "name_ja", "slug", "icon_emoji", "description"])
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
        # UserPinnedBadge không khai ở NATURAL_KEYS -> lùi về unique_together.
        self.assertEqual(dataio.duplicate_fields(UserPinnedBadge), ("user", "category"))

    def test_every_table_has_a_natural_key_except_the_log_tables(self):
        """Bảng không có khoá thì nhập lại cùng một file là nhân đôi dữ liệu.

        Đúng ba bảng NHẬT KÝ được phép không có khoá, và chúng phải nằm trong
        danh sách khai báo tường minh chứ không phải vô tình thiếu."""
        without = {
            dataio.model_label(m)
            for m in dataio.importable_models()
            if not dataio.natural_key_fields(m)
        }
        self.assertEqual(without, set(dataio.TABLES_WITHOUT_NATURAL_KEY))

    def test_example_sentence_is_no_longer_duplicated_on_reimport(self):
        self.assertEqual(
            dataio.duplicate_fields(ExampleSentence), ("vocabulary", "sentence_jp")
        )

    def test_no_column_asks_for_a_raw_id_when_the_target_has_a_natural_key(self):
        """Trước đây wordlist_id / sheet_id / contribution_id bắt admin gõ id thô.

        Giờ khoá tự nhiên được trải phẳng qua nhiều cấp FK. Còn đúng một cột id
        thô — contribution_id — vì Contribution cố ý không có khoá tự nhiên."""
        raw_id_columns = []
        for model in dataio.importable_models():
            for column in dataio.columns_for(model):
                if column.is_fk and column.lookup is None:
                    raw_id_columns.append(f"{dataio.model_label(model)}.{column.header}")
        self.assertEqual(
            raw_id_columns, ["gamification.userpointtransaction.contribution_id"]
        )

    def test_natural_key_is_flattened_through_several_foreign_keys(self):
        self.assertEqual(
            dataio.headers_for(UserWordlistWord),
            [
                "wordlist__user__username",
                "wordlist__name",
                "vocabulary__word",
                "vocabulary__reading",
            ],
        )
        self.assertEqual(
            dataio.headers_for(PracticeSheetWord),
            [
                "sheet__user__username",
                "sheet__pdf_file",
                "vocabulary__word",
                "vocabulary__reading",
            ],
        )

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
        self.assertEqual(body, "name,name_ja,slug,icon_emoji,description")

    def test_xlsx_export_returns_current_rows(self):
        Topic.objects.create(name="Nhà hàng", slug="nha-hang", name_ja="レストラン")
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse("admin_panel:data_export", args=["vocabulary.topic", "xlsx"])
        )
        self.assertEqual(response.status_code, 200)
        headers, rows = dataio.read_table(response.content, "x.xlsx")
        self.assertEqual(headers, ["name", "name_ja", "slug", "icon_emoji", "description"])
        self.assertEqual([r[1] for r in rows], ["レストラン"])
        self.assertEqual([r[2] for r in rows], ["nha-hang"])

    # -- xem trước ----------------------------------------------------------
    def test_preview_classifies_rows_and_writes_nothing(self):
        Topic.objects.create(name="Nhà hàng", slug="nha-hang")
        self.client.force_login(self.admin)
        upload = csv_upload(
            "topics.csv",
            ["name", "name_ja", "slug", "icon_emoji", "description"],
            ["Sân bay", "空港", "san-bay", "", ""],       # mới
            ["Nhà hàng", "", "nha-hang", "", ""],         # trùng slug -> bỏ qua
            ["", "", "thieu-ten", "", ""],                # thiếu name -> lỗi
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
                ["name", "name_ja", "slug", "icon_emoji", "description"],
                ["Sân bay", "空港", "san-bay", "", ""],
                ["Nhà hàng", "", "nha-hang", "", ""],
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
            csv_upload("t.csv", ["name", "name_ja", "slug", "icon_emoji", "description"], ["Sân bay", "空港", "san-bay", "", ""]),
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
            word="予約", reading="よやく", meaning_vi="đặt chỗ",
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
            {"data_file": csv_upload("t.csv", ["name", "name_ja", "slug", "icon_emoji", "description"], ["Sân bay", "空港", "san-bay", "", ""])},
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


class DataWriteModeTests(AdminPanelTestCase):
    """Ba chế độ ghi: chỉ thêm / thêm + cập nhật / chỉ cập nhật (14/09/2026)."""

    HEADER = ["name", "name_ja", "slug", "icon_emoji", "description"]

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="sieuquantri", password="MatKhauRatManh123", email="a@b.c",
        )
        self.client.force_login(self.admin)
        self.url = reverse("admin_panel:data_import", args=["vocabulary.topic"])
        self.confirm_url = reverse("admin_panel:data_import_confirm", args=["vocabulary.topic"])
        Topic.objects.create(name="Nhà hàng", name_ja="レストラン", slug="nha-hang")

    def _run(self, mode, upload):
        response = self.client.post(self.url, {"data_file": upload, "mode": mode})
        report = response.context["report"]
        token = response.context["token"]
        if token:
            self.client.post(self.confirm_url, {"token": token})
        return report

    def test_insert_mode_leaves_the_existing_row_untouched(self):
        self._run(
            dataio.MODE_INSERT,
            csv_upload("t.csv", self.HEADER, ["Quán ăn", "食堂", "nha-hang", "", ""]),
        )
        self.assertEqual(Topic.objects.get(slug="nha-hang").name, "Nhà hàng")

    def test_upsert_mode_overwrites_the_existing_row_and_adds_the_new_one(self):
        report = self._run(
            dataio.MODE_UPSERT,
            csv_upload(
                "t.csv",
                self.HEADER,
                ["Quán ăn", "食堂", "nha-hang", "", ""],
                ["Sân bay", "空港", "san-bay", "", ""],
            ),
        )
        self.assertEqual((report.new_count, report.update_count), (1, 1))
        self.assertEqual(Topic.objects.get(slug="nha-hang").name, "Quán ăn")
        self.assertTrue(Topic.objects.filter(slug="san-bay").exists())

    def test_update_mode_skips_rows_that_do_not_exist_yet(self):
        report = self._run(
            dataio.MODE_UPDATE,
            csv_upload(
                "t.csv",
                self.HEADER,
                ["Quán ăn", "食堂", "nha-hang", "", ""],
                ["Sân bay", "空港", "san-bay", "", ""],
            ),
        )
        self.assertEqual((report.new_count, report.update_count, report.missing_count), (0, 1, 1))
        self.assertFalse(Topic.objects.filter(slug="san-bay").exists())
        self.assertEqual(Topic.objects.get(slug="nha-hang").name, "Quán ăn")

    def test_update_mode_only_needs_the_key_columns(self):
        """Sửa mỗi một cột thì file chỉ cần cột khoá + cột đó. Cột không có
        trong file phải GIỮ NGUYÊN giá trị cũ, không bị xoá trắng."""
        report = self._run(
            dataio.MODE_UPDATE,
            csv_upload("t.csv", ["slug", "name"], ["nha-hang", "Quán ăn"]),
        )
        self.assertEqual(report.missing_columns, [])
        self.assertIn("name_ja", report.ignored_columns)
        topic = Topic.objects.get(slug="nha-hang")
        self.assertEqual(topic.name, "Quán ăn")
        self.assertEqual(topic.name_ja, "レストラン")  # cột vắng mặt -> không đụng

    def test_a_table_without_a_natural_key_refuses_update_modes(self):
        """Contribution cố ý không có khoá tự nhiên. Nếu vẫn cho chạy chế độ ghi
        đè thì nó sẽ ghi đè nhầm một bản ghi lịch sử hợp lệ."""
        url = reverse("admin_panel:data_import", args=["gamification.contribution"])
        response = self.client.get(url)
        self.assertEqual(response.context["available_modes"], [dataio.MODE_INSERT])
        response = self.client.post(
            url,
            {
                "mode": dataio.MODE_UPSERT,
                "data_file": csv_upload("c.csv", ["user__username"], ["sieuquantri"]),
            },
        )
        self.assertIsNone(response.context.get("report"))

    def test_confirm_takes_the_mode_from_the_session_not_the_form(self):
        """Sửa tay ô hidden không được phép biến 'chỉ thêm' đã xem trước thành
        'ghi đè'."""
        response = self.client.post(
            self.url,
            {
                "data_file": csv_upload("t.csv", self.HEADER, ["Sân bay", "空港", "san-bay", "", ""]),
                "mode": dataio.MODE_INSERT,
            },
        )
        self.client.post(
            self.confirm_url,
            {"token": response.context["token"], "mode": dataio.MODE_UPSERT},
        )
        self.assertEqual(Topic.objects.get(slug="nha-hang").name, "Nhà hàng")
        self.assertTrue(Topic.objects.filter(slug="san-bay").exists())

    def test_update_never_wipes_a_password_when_the_cell_is_blank(self):
        """Ô password trống ở dòng CẬP NHẬT = giữ nguyên. Nếu không, nhập lại
        danh sách người dùng là khoá tài khoản của tất cả mọi người."""
        learner = User.objects.get(username="nguoihoc")
        old_hash = learner.password
        url = reverse("admin_panel:data_import", args=["accounts.user"])
        headers = dataio.headers_for(User)
        row = ["" for _ in headers]
        row[headers.index("username")] = "nguoihoc"
        row[headers.index("first_name")] = "Tên Mới"
        response = self.client.post(
            url, {"data_file": csv_upload("u.csv", headers, row), "mode": dataio.MODE_UPSERT}
        )
        self.client.post(
            reverse("admin_panel:data_import_confirm", args=["accounts.user"]),
            {"token": response.context["token"]},
        )
        learner.refresh_from_db()
        self.assertEqual(learner.first_name, "Tên Mới")
        self.assertEqual(learner.password, old_hash)
        self.assertTrue(learner.check_password("MatKhauRatManh123"))


class FullVocabularyDatasetTests(AdminPanelTestCase):
    """Mẫu gộp: 1 dòng = 1 từ vựng trọn vẹn trên 3 bảng."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="sieuquantri", password="MatKhauRatManh123", email="a@b.c",
        )
        self.client.force_login(self.admin)
        self.label = dataio.FULL_VOCAB_LABEL
        self.url = reverse("admin_panel:data_import", args=[self.label])
        self.confirm_url = reverse("admin_panel:data_import_confirm", args=[self.label])
        self.headers = dataio.full_vocab_headers()
        Topic.objects.create(name="Họp hành", name_ja="会議・打合せ", slug="hop-hanh")
        Topic.objects.create(name="Điện thoại", name_ja="電話応対", slug="dien-thoai")

    def _row(self, **values):
        row = ["" for _ in self.headers]
        for key, value in values.items():
            row[self.headers.index(key)] = value
        return row

    def _run(self, mode, *rows):
        upload = csv_upload("v.csv", self.headers, *rows)
        response = self.client.post(self.url, {"data_file": upload, "mode": mode})
        report = response.context["report"]
        if response.context["token"]:
            self.client.post(self.confirm_url, {"token": response.context["token"]})
        return report

    def test_headers_cover_all_three_tables(self):
        self.assertEqual(
            self.headers,
            [
                "word", "reading", "meaning_vi", "audio_url", "topics",
                "example1_jp", "example1_vi",
                "example2_jp", "example2_vi",
                "example3_jp", "example3_vi",
            ],
        )

    def test_it_shows_up_in_the_table_list(self):
        labels = [t["label"] for t in self.client.get(reverse("admin_panel:data_index")).context["tables"]]
        self.assertEqual(labels[0], self.label)
        self.assertEqual(len(labels), 20)  # 19 bảng + 1 mẫu gộp

    def test_one_row_writes_word_topics_and_examples(self):
        report = self._run(
            dataio.MODE_INSERT,
            self._row(
                word="打ち合わせ", reading="うちあわせ", meaning_vi="buổi họp",
                topics="hop-hanh;dien-thoai",
                example1_jp="明日打ち合わせがあります。", example1_vi="Ngày mai có buổi họp.",
            ),
        )
        self.assertEqual(report.new_count, 1)
        vocab = Vocabulary.objects.get(word="打ち合わせ", reading="うちあわせ")
        self.assertEqual(
            sorted(VocabularyTopic.objects.filter(vocabulary=vocab).values_list("topic__slug", flat=True)),
            ["dien-thoai", "hop-hanh"],
        )
        self.assertEqual(vocab.examples.count(), 1)
        # Ghi qua save() nên audit còn nguyên, kể cả ở bảng nối.
        self.assertEqual(VocabularyTopic.objects.first().created_by, self.admin)
        self.assertEqual(ExampleSentence.objects.first().created_by, self.admin)

    def test_an_unknown_topic_slug_is_a_row_error_and_nothing_is_written(self):
        report = self._run(
            dataio.MODE_INSERT,
            self._row(word="見積もり", reading="みつもり", meaning_vi="báo giá", topics="khong-co-that"),
        )
        self.assertEqual(report.error_count, 1)
        self.assertFalse(report.can_apply)
        self.assertEqual(Vocabulary.objects.count(), 0)

    def test_an_example_needs_both_halves(self):
        report = self._run(
            dataio.MODE_INSERT,
            self._row(word="見積もり", reading="みつもり", meaning_vi="báo giá", example1_jp="見積もりをお願いします。"),
        )
        self.assertEqual(report.error_count, 1)

    def test_reimporting_the_same_file_adds_nothing(self):
        row = self._row(
            word="承知しました", reading="しょうちしました", meaning_vi="tôi hiểu rồi",
            topics="hop-hanh",
            example1_jp="承知しました。", example1_vi="Tôi hiểu rồi.",
        )
        self._run(dataio.MODE_INSERT, row)
        self._run(dataio.MODE_UPSERT, row)
        self.assertEqual(Vocabulary.objects.count(), 1)
        self.assertEqual(VocabularyTopic.objects.count(), 1)
        self.assertEqual(ExampleSentence.objects.count(), 1)

    def test_upsert_updates_the_meaning_and_only_adds_missing_children(self):
        self._run(
            dataio.MODE_INSERT,
            self._row(
                word="納品", reading="のうひん", meaning_vi="giao hang",
                topics="hop-hanh",
                example1_jp="納品は明日です。", example1_vi="Giao hàng vào ngày mai.",
            ),
        )
        report = self._run(
            dataio.MODE_UPSERT,
            self._row(
                word="納品", reading="のうひん", meaning_vi="giao hàng / nộp hàng",
                topics="dien-thoai",
                example2_jp="納品書を送ります。", example2_vi="Tôi sẽ gửi phiếu giao hàng.",
            ),
        )
        self.assertEqual(report.update_count, 1)
        vocab = Vocabulary.objects.get(word="納品")
        self.assertEqual(vocab.meaning_vi, "giao hàng / nộp hàng")
        # chủ đề cũ KHÔNG bị gỡ, chủ đề mới được thêm
        self.assertEqual(
            sorted(VocabularyTopic.objects.filter(vocabulary=vocab).values_list("topic__slug", flat=True)),
            ["dien-thoai", "hop-hanh"],
        )
        self.assertEqual(vocab.examples.count(), 2)

    def test_export_round_trips_through_the_import(self):
        self._run(
            dataio.MODE_INSERT,
            self._row(
                word="請求書", reading="せいきゅうしょ", meaning_vi="hoá đơn",
                topics="hop-hanh", example1_jp="請求書を送付します。", example1_vi="Tôi gửi hoá đơn.",
            ),
        )
        response = self.client.get(reverse("admin_panel:data_export", args=[self.label, "csv"]))
        headers, rows = dataio.read_table(response.content, "x.csv")
        self.assertEqual(headers, self.headers)
        self.assertEqual(rows[0][headers.index("topics")], "hop-hanh")
        self.assertEqual(rows[0][headers.index("example1_vi")], "Tôi gửi hoá đơn.")

    def test_it_needs_permission_on_all_three_tables(self):
        """Quyền trên bảng câu ví dụ thành vô nghĩa nếu mẫu gộp chỉ kiểm tra
        quyền trên bảng từ vựng."""
        from django.contrib.auth.models import Permission

        self.client.force_login(self.staff)
        for codename in ("add_vocabulary", "add_vocabularytopic"):
            self.staff.user_permissions.add(Permission.objects.get(codename=codename))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.staff.user_permissions.add(Permission.objects.get(codename="add_examplesentence"))
        self.staff = User.objects.get(pk=self.staff.pk)  # xoá cache quyền
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class SampleFileTests(TestCase):
    """File mẫu kèm trong repo phải khớp bộ cột thật.

    Bản cũ còn cột "Cap do BJT" sau khi cấp độ BJT đã bị gỡ khỏi DB ngày
    13/09 — admin tải về điền theo là chắc chắn nhập lỗi. Test này khoá lại:
    đổi cột trong models.py mà quên sinh lại file mẫu thì đỏ ngay.
    """

    SAMPLE = "mau_danh_sach_tu_vung"

    def _path(self, suffix):
        from django.conf import settings

        return Path(settings.BASE_DIR) / "htmlTemplate" / f"{self.SAMPLE}.{suffix}"

    def test_csv_sample_matches_the_full_vocabulary_template(self):
        headers, rows = dataio.read_table(self._path("csv").read_bytes(), "x.csv")
        self.assertEqual(headers, dataio.full_vocab_headers())
        self.assertTrue(rows)

    def test_xlsx_sample_matches_the_full_vocabulary_template(self):
        headers, rows = dataio.read_table(self._path("xlsx").read_bytes(), "x.xlsx")
        self.assertEqual(headers, dataio.full_vocab_headers())
        self.assertTrue(rows)

    def test_sample_only_uses_topic_slugs_that_the_seed_file_defines(self):
        """Slug trong file mẫu phải có thật trong docs/data/mau_chu_de.csv,
        không thì nhập file mẫu vào là ra một loạt dòng lỗi."""
        from django.conf import settings

        seed = Path(settings.BASE_DIR) / "docs" / "data" / "mau_chu_de.csv"
        seed_headers, seed_rows = dataio.read_table(seed.read_bytes(), "x.csv")
        known = {row[seed_headers.index("slug")].strip() for row in seed_rows}

        headers, rows = dataio.read_table(self._path("csv").read_bytes(), "x.csv")
        position = headers.index(dataio.FULL_VOCAB_TOPIC_COLUMN)
        used = set()
        for row in rows:
            used.update(s.strip() for s in row[position].split(";") if s.strip())
        self.assertTrue(used)
        self.assertEqual(used - known, set())

    def test_no_sample_file_still_mentions_the_removed_bjt_level(self):
        for suffix in ("csv", "xlsx"):
            headers, _ = dataio.read_table(self._path(suffix).read_bytes(), f"x.{suffix}")
            joined = " ".join(headers).lower()
            self.assertNotIn("bjt", joined)
            self.assertNotIn("cap do", joined)
