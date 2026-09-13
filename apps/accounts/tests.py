"""
Test cho SC01_DangNhap và SC02_DangKy.

Chạy: python manage.py test apps.accounts
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.core.properties import message

User = get_user_model()


class AccountsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        # MasterCode nuôi choices của target_bjt_level / ui_theme — thiếu nó thì
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
            "target_bjt_level": "J4",
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
        self.assertEqual(user.target_bjt_level, "J4")
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
