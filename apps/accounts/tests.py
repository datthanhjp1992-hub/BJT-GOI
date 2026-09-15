"""
Test cho SC01_DangNhap, SC02_DangKy và SC08_CaiDat.

Chạy: python manage.py test apps.accounts
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.properties import message
from apps.learning.models import StudySession, UserVocabularyProgress
from apps.learning import services as learning_services
from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic

User = get_user_model()


class AccountsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # MasterCode nuôi choices của ui_theme — thiếu nó thì
        # <select> rỗng và form không validate được.
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        # apps.core.mastercode cache theo tiến trình; xoá để test không dính
        # dữ liệu của test trước.
        cache.clear()


class LoginViewTests(AccountsTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="dat", email="dat@example.com", password="MatKhauRatManh123",
            first_name="Nguyễn Thành Đạt",
        )

    def test_get_renders_login_page(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_with_username(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": "dat", "password": "MatKhauRatManh123"},
        )
        self.assertRedirects(response, reverse("learning:dashboard"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_login_with_email(self):
        """Ô đầu tiên nhận cả email — đúng nhãn accounts.login.field.username."""
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": "DAT@example.com", "password": "MatKhauRatManh123"},
        )
        self.assertRedirects(response, reverse("learning:dashboard"))

    def test_wrong_password_shows_message_from_properties(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"identifier": "dat", "password": "sai-mat-khau"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("accounts.login.error.invalid_credentials"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_next_param_is_honoured(self):
        target = reverse("vocabulary:index")
        response = self.client.post(
            reverse("accounts:login") + "?next=" + target,
            {"identifier": "dat", "password": "MatKhauRatManh123", "next": target},
        )
        self.assertRedirects(response, target)

    def test_open_redirect_is_rejected(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "identifier": "dat",
                "password": "MatKhauRatManh123",
                "next": "https://trang-la.example.com/lua-dao",
            },
        )
        self.assertRedirects(response, reverse("learning:dashboard"))

    def test_authenticated_user_is_redirected_away(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:login"))
        self.assertRedirects(response, reverse("learning:dashboard"))


class LogoutViewTests(AccountsTestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(username="dat", password="MatKhauRatManh123")
        self.client.force_login(self.user)

    def test_get_is_not_allowed(self):
        """Đăng xuất bằng GET là lỗ hổng CSRF — view chỉ nhận POST."""
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)

    def test_post_logs_out(self):
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotIn("_auth_user_id", self.client.session)


class RegisterViewTests(AccountsTestCase):
    def _payload(self, **overrides):
        data = {
            "full_name": "Nguyễn Văn A",
            "username": "nguyenvana",
            "email": "a@example.com",
            "password": "MatKhauRatManh123",
            "confirm_password": "MatKhauRatManh123",
        }
        data.update(overrides)
        return data

    def test_get_renders_register_page(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/register.html")

    def test_register_creates_user_and_logs_in(self):
        response = self.client.post(reverse("accounts:register"), self._payload())
        self.assertRedirects(response, reverse("learning:dashboard"))

        user = User.objects.get(username="nguyenvana")
        self.assertTrue(user.check_password("MatKhauRatManh123"))
        # Họ tên tiếng Việt giữ nguyên thứ tự, dồn vào first_name.
        self.assertEqual(user.first_name, "Nguyễn Văn A")
        self.assertEqual(user.last_name, "")
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_password_mismatch_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"),
            self._payload(confirm_password="KhacHoanToan123"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("common.validation.password_mismatch"))
        self.assertFalse(User.objects.filter(username="nguyenvana").exists())

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(username="cu", email="a@example.com", password="x")
        response = self.client.post(reverse("accounts:register"), self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("accounts.register.error.email_taken"))

    def test_duplicate_username_is_rejected(self):
        User.objects.create_user(username="nguyenvana", password="x")
        response = self.client.post(reverse("accounts:register"), self._payload())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("accounts.register.error.username_taken"))

    def test_weak_password_is_rejected(self):
        response = self.client.post(
            reverse("accounts:register"),
            self._payload(password="123", confirm_password="123"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="nguyenvana").exists())


class ThemeRenderingTests(AccountsTestCase):
    """base.html phải nạp đúng file CSS theo User.ui_theme (A/B/C).

    Đây là chỗ dễ vỡ nhất khi thêm màn hình mới: template chỉ được dùng token
    và class chung, nên nếu một theme thiếu token thì trang vẫn render nhưng
    mất màu. Test này giữ phần "chọn đúng file"; phần "đủ token" được bảo đảm
    bằng khối bổ sung cuối mỗi file static/css/theme_*.css.
    """

    def test_each_theme_loads_its_own_stylesheet(self):
        # So khớp theo TIỀN TỐ chứ không phải nguyên tên file: trên production
        # WhiteNoise dùng ManifestStaticFilesStorage nên href thật là
        # "theme_a.<hash>.css". Ràng cứng ".css" là test xanh ở local, đỏ khi
        # chạy đúng cấu hình production.
        for theme, expected in (("A", "theme_a"), ("B", "theme_b"), ("C", "theme_c")):
            with self.subTest(theme=theme):
                user = User.objects.create_user(
                    username="user" + theme, password="MatKhauRatManh123", ui_theme=theme,
                )
                self.client.force_login(user)
                response = self.client.get(reverse("learning:dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, expected)

    def test_anonymous_pages_fall_back_to_theme_a(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, "theme_a")

    def test_invalid_theme_falls_back_instead_of_crashing(self):
        """ui_theme rỗng/lạ không được làm 500 cả trang.

        base.html nối chuỗi thành tên file CSS; với ManifestStaticFilesStorage
        một tên không có trong manifest sẽ ném ValueError.
        """
        user = User.objects.create_user(username="loi", password="MatKhauRatManh123")
        User.objects.filter(pk=user.pk).update(ui_theme="")
        self.client.force_login(user)
        response = self.client.get(reverse("learning:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "theme_a")


class SettingsViewTests(AccountsTestCase):
    """SC08_CaiDat — hai form độc lập trên cùng một URL."""

    PASSWORD = "MatKhauRatManh123"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="dat", email="dat@example.com", password=self.PASSWORD,
            ui_theme="A", daily_review_goal=20, timezone="Asia/Tokyo",
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:settings")

    def _prefs(self, **overrides):
        data = {
            "section": "preferences",
            "ui_theme": "A",
            "daily_review_goal": "20",
            "timezone": "Asia/Tokyo",
        }
        data.update(overrides)
        return data

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_get_renders_one_card_per_theme(self):
        """Thẻ chọn giao diện dựng từ MasterCode, không liệt kê cứng A/B/C."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/settings.html")
        # "Washi & Vermillion" ra HTML thành "Washi &amp; Vermillion" — so khớp
        # phần không có ký tự phải escape.
        for name in ("Washi", "Studio Mono", "Genki Playful"):
            self.assertContains(response, name)
        self.assertEqual(response.content.decode().count('class="choice-card"'), 3)

    def test_saving_preferences_updates_user(self):
        response = self.client.post(self.url, self._prefs(
            daily_review_goal="35",
            timezone="Asia/Ho_Chi_Minh",
            daily_reminder_enabled="on",
        ))
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_review_goal, 35)
        self.assertEqual(self.user.timezone, "Asia/Ho_Chi_Minh")
        self.assertTrue(self.user.daily_reminder_enabled)
        # Checkbox không gửi lên = tắt; đây là hành vi mặc định của HTML form,
        # test để không ai "sửa" thành giữ nguyên giá trị cũ.
        self.assertFalse(self.user.weekly_email_summary_enabled)

    def test_changing_theme_flashes_name_from_mastercode(self):
        response = self.client.post(self.url, self._prefs(ui_theme="C"), follow=True)
        self.user.refresh_from_db()
        self.assertEqual(self.user.ui_theme, "C")
        self.assertContains(response, message(
            "accounts.settings.success.theme_updated", theme_name="Genki Playful",
        ))
        # Đổi theme phải kéo theo file CSS khác ngay ở lần render kế tiếp.
        self.assertContains(response, "theme_c")

    def test_goal_outside_range_is_rejected(self):
        for bad in ("0", "500"):
            with self.subTest(goal=bad):
                response = self.client.post(self.url, self._prefs(daily_review_goal=bad))
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertEqual(self.user.daily_review_goal, 20)

    def test_unknown_timezone_is_rejected(self):
        """Giá trị lạ phải bị chặn ở form — User.tzinfo sẽ âm thầm rơi về
        TIME_ZONE của server, nên lưu được giá trị rác là bug lặng lẽ."""
        response = self.client.post(self.url, self._prefs(timezone="Mars/Olympus"))
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.timezone, "Asia/Tokyo")

    def test_password_change_keeps_session(self):
        response = self.client.post(self.url, {
            "section": "password",
            "old_password": self.PASSWORD,
            "new_password1": "MatKhauMoiRatManh456",
            "new_password2": "MatKhauMoiRatManh456",
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("MatKhauMoiRatManh456"))
        # Thiếu update_session_auth_hash thì người dùng bị đá ra login ngay sau
        # khi đổi mật khẩu thành công.
        self.assertIn("_auth_user_id", self.client.session)

    def test_wrong_current_password_is_rejected(self):
        response = self.client.post(self.url, {
            "section": "password",
            "old_password": "sai-mat-khau",
            "new_password1": "MatKhauMoiRatManh456",
            "new_password2": "MatKhauMoiRatManh456",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.PASSWORD))

    def test_password_form_does_not_touch_preferences(self):
        """Hai form tách nhau: gửi khu mật khẩu không được coi là khu tuỳ chọn
        gửi rỗng (nếu gộp chung, daily_review_goal sẽ thành "bắt buộc nhập")."""
        self.client.post(self.url, {
            "section": "password",
            "old_password": "sai-mat-khau",
            "new_password1": "x",
            "new_password2": "x",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_review_goal, 20)
        self.assertEqual(self.user.ui_theme, "A")


class ProfileViewTests(AccountsTestCase):
    """SC09_ThongTinCaNhan."""

    PASSWORD = "MatKhauRatManh123"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="dat", email="dat@example.com", password=self.PASSWORD,
            first_name="Nguyễn Thành Đạt",
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts:profile")

    def _make_topic(self, name, slug, words):
        topic = Topic.objects.create(name=name, slug=slug)
        for word in words:
            vocab = Vocabulary.objects.create(word=word, reading=word, meaning_vi="nghĩa " + word)
            VocabularyTopic.objects.create(vocabulary=vocab, topic=topic)
        return topic

    def test_requires_login(self):
        self.client.logout()
        self.assertRedirects(
            self.client.get(self.url), reverse("accounts:login") + "?next=" + self.url
        )

    def test_renders_for_brand_new_user(self):
        """Chưa học gì cả thì trang vẫn phải ra 200, không 500 vì recent_topics rỗng."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/profile.html")
        self.assertEqual(response.context["recent_topics"], [])

    def test_shows_stats_and_points(self):
        self.user.total_points = 42
        self.user.save(update_fields=["total_points"])
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文", "予約"])
        vocab = topic.vocabularies.first()
        UserVocabularyProgress.objects.create(user=self.user, vocabulary=vocab, is_mastered=True)

        response = self.client.get(self.url)

        self.assertEqual(response.context["stats"]["words_mastered"], 1)
        self.assertContains(response, "42")

    def test_lists_recent_topics_newest_session_first(self):
        older = self._make_topic("Gia đình", "gia-dinh", ["家族"])
        newer = self._make_topic("Công việc", "cong-viec", ["会議", "報告"])
        StudySession.objects.create(
            user=self.user, topic=older, session_type="flashcard",
            started_at=self.user.local_now() - __import__("datetime").timedelta(days=3),
        )
        StudySession.objects.create(
            user=self.user, topic=newer, session_type="flashcard", started_at=self.user.local_now(),
        )

        response = self.client.get(self.url)

        slugs = [row["topic"].slug for row in response.context["recent_topics"]]
        self.assertEqual(slugs, ["cong-viec", "gia-dinh"])
        self.assertEqual(response.context["recent_topics"][0]["total"], 2)

    def test_does_not_show_the_removed_bjt_level_field(self):
        """Cấp độ BJT đã bị bỏ 13/09/2026 — mockup SC09 còn sót ô này, form
        thật không được có, xem apps.accounts.forms.ProfileForm."""
        response = self.client.get(self.url)
        self.assertNotContains(response, "Trình độ mục tiêu")

    def test_updates_full_name_and_email(self):
        response = self.client.post(self.url, {
            "full_name": "Tên Mới", "email": "moi@example.com",
        })
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Tên Mới")
        self.assertEqual(self.user.email, "moi@example.com")

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(username="khac", email="da-co@example.com", password=self.PASSWORD)
        response = self.client.post(self.url, {
            "full_name": self.user.first_name, "email": "da-co@example.com",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "dat@example.com")


class RecentTopicsServiceTests(AccountsTestCase):
    """apps.learning.services.get_recent_topics — nguồn dữ liệu của SC09."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username="dat", password="MatKhauRatManh123",
        )

    def _make_topic(self, name, slug, words):
        topic = Topic.objects.create(name=name, slug=slug)
        for word in words:
            vocab = Vocabulary.objects.create(word=word, reading=word, meaning_vi="nghĩa " + word)
            VocabularyTopic.objects.create(vocabulary=vocab, topic=topic)
        return topic

    def test_empty_when_user_has_no_sessions(self):
        self.assertEqual(learning_services.get_recent_topics(self.user), [])

    def test_deduplicates_repeated_sessions_of_the_same_topic(self):
        topic = self._make_topic("Nhà hàng", "nha-hang", ["注文"])
        StudySession.objects.create(user=self.user, topic=topic, session_type="flashcard", started_at=self.user.local_now())
        StudySession.objects.create(user=self.user, topic=topic, session_type="quiz", started_at=self.user.local_now())

        result = learning_services.get_recent_topics(self.user)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["topic"], topic)

    def test_respects_limit(self):
        for i in range(3):
            topic = self._make_topic(f"Chủ đề {i}", f"chu-de-{i}", [f"単語{i}"])
            StudySession.objects.create(user=self.user, topic=topic, session_type="flashcard", started_at=self.user.local_now())

        result = learning_services.get_recent_topics(self.user, limit=2)

        self.assertEqual(len(result), 2)


class ThemeCssContractTests(TestCase):
    """Ba file theme_*.css phải cùng cung cấp những gì SC08 cần.

    Bẫy thật: `input,select{width:100%;padding:12px 14px}` khai ở đầu cả 3 file
    áp cho MỌI input, nên checkbox/radio bị kéo giãn hết chiều ngang card. Ba
    file mockup gốc né bằng style="width:auto" viết tay từng thẻ, bản Django
    render input từ form nên bắt buộc phải sửa ở CSS.
    """

    REQUIRED_RULES = (
        "input[type=checkbox]",
        "input[type=radio]",
        ".checkbox-row",
        ".choice-grid",
        ".choice-card",
        '.swatch[data-theme="a"]',
        '.swatch[data-theme="b"]',
        '.swatch[data-theme="c"]',
    )

    def test_every_theme_defines_settings_rules(self):
        for name in ("theme_a.css", "theme_b.css", "theme_c.css"):
            css = (Path(settings.BASE_DIR) / "static" / "css" / name).read_text(
                encoding="utf-8"
            )
            for rule in self.REQUIRED_RULES:
                with self.subTest(file=name, rule=rule):
                    self.assertIn(rule, css, msg=f"{name} thiếu rule {rule} cho SC08")
