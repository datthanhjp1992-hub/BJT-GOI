"""
Test cho SC10_LuyenVietPdf — trọng tâm là VIỆC TÌM FONT.

Bối cảnh: bản đầu của pdf_generator.py gọi `pdfmetrics.registerFont()` ngay ở
cấp module với đường dẫn /usr/share/fonts/... hardcode. Vì config/urls.py có
`include("apps.practice_sheets.urls")`, chỉ cần máy chủ thiếu font là mọi thứ
chết theo — kể cả `manage.py check` và `collectstatic`. Đó chính là thứ làm
build Render đỏ ngày 13/09. Các test dưới đây khoá lại hành vi đúng.
"""
import importlib
import os
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.properties import message
from apps.practice_sheets import pdf_generator
from apps.vocabulary.models import Vocabulary

User = get_user_model()


class FontResolutionTests(TestCase):
    def setUp(self):
        # _ensure_fonts_registered() nhớ kết quả bằng cờ toàn cục; reset để mỗi
        # test tự chạy lại phần dò font.
        pdf_generator._fonts_registered = False
        pdf_generator._jp_font_path_cache = None
        pdf_generator._jp_font_cache.clear()

    def test_module_imports_even_when_no_font_exists(self):
        """Không có bất kỳ file font nào thì import module vẫn phải trót lọt.

        Đây là test quan trọng nhất của file: import mà nổ là sập toàn site,
        không riêng tính năng PDF.
        """
        self.addCleanup(importlib.reload, pdf_generator)
        with mock.patch("os.path.isfile", return_value=False):
            importlib.reload(pdf_generator)  # không được ném exception

    def test_missing_font_raises_clear_error_at_generate_time(self):
        with mock.patch.object(pdf_generator, "_search_dirs", return_value=[]), \
                mock.patch.object(pdf_generator, "_VI_FONTS", {
                    "KhongTonTai": ("KhongTonTai.ttf", ["/khong/co/that.ttf"]),
                }):
            with self.assertRaises(pdf_generator.PracticeSheetFontError) as ctx:
                pdf_generator._ensure_fonts_registered()
        # Thông báo phải nói được cách xử lý, không chỉ "file not found".
        self.assertIn("assets/fonts", str(ctx.exception))

    def test_bundled_font_dir_wins_over_system_path(self):
        """Font kèm repo phải được ưu tiên hơn font hệ thống — đó là cách duy
        nhất để chạy trên PaaS không cho cài gói."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            bundled = Path(tmp) / "assets" / "fonts"
            bundled.mkdir(parents=True)
            fake = bundled / "DejaVuSans.ttf"
            fake.write_bytes(b"not-a-real-font")

            with override_settings(BASE_DIR=tmp):
                resolved = pdf_generator._resolve_font(
                    "DejaVuSans.ttf", ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
                )
            self.assertEqual(resolved, str(fake))

    def test_env_var_wins_over_everything(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "DejaVuSans.ttf"
            fake.write_bytes(b"not-a-real-font")
            with mock.patch.dict(os.environ, {"PRACTICE_SHEET_FONT_DIR": tmp}):
                resolved = pdf_generator._resolve_font("DejaVuSans.ttf", ["/khong/co/that.ttf"])
            self.assertEqual(resolved, str(fake))


class GeneratePdfTests(TestCase):
    """Chỉ chạy khi máy đang test thực sự có font — CI/sandbox thường thiếu."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        pdf_generator._fonts_registered = False
        pdf_generator._jp_font_path_cache = None
        pdf_generator._jp_font_cache.clear()
        try:
            pdf_generator._ensure_fonts_registered()
            pdf_generator._jp_font(12)
        except pdf_generator.PracticeSheetFontError as exc:
            self.skipTest(str(exc))

    def test_generates_a_real_pdf(self):
        words = [
            Vocabulary.objects.create(
                word="注文する", reading="ちゅうもんする", meaning_vi="gọi món",
            ),
            Vocabulary.objects.create(
                word="予約", reading="よやく", meaning_vi="đặt chỗ trước",
            ),
        ]
        filename, content = pdf_generator.generate_practice_pdf(words)
        self.assertEqual(filename, "phieu_luyen_viet.pdf")
        data = content.read()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertGreater(len(data), 1000)


class CreateViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="dat", password="MatKhauRatManh123")
        self.client.force_login(self.user)

    def test_requires_login(self):
        self.client.logout()
        url = reverse("practice_sheets:create")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_get_renders(self):
        self.assertEqual(self.client.get(reverse("practice_sheets:create")).status_code, 200)

    def test_font_error_shows_message_instead_of_500(self):
        vocab = Vocabulary.objects.create(
            word="予約", reading="よやく", meaning_vi="đặt chỗ",
        )
        with mock.patch(
            "apps.practice_sheets.views.generate_practice_pdf",
            side_effect=pdf_generator.PracticeSheetFontError("thiếu font"),
        ):
            response = self.client.post(
                reverse("practice_sheets:create"),
                {"word_ids": [vocab.pk], "lines_per_word": 2},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("practice_sheets.generate.error.font_missing"))
        # Không được tạo bản ghi rỗng khi PDF sinh hỏng.
        self.assertEqual(self.user.practice_sheets.count() if hasattr(self.user, "practice_sheets") else 0, 0)
