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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core import dataio
from apps.core.constants import (
    RECALL_JP_TO_VI,
    RECALL_MIXED,
    RECALL_VI_TO_JP,
    SHEET_TYPE_RECALL,
    SHEET_TYPE_WRITING,
)
from apps.core.properties import message
from apps.practice_sheets import pdf_generator, wordsource
from apps.practice_sheets.models import PracticeSheet, PracticeSheetWord
from apps.vocabulary.models import Topic, Vocabulary, VocabularyTopic

User = get_user_model()



def _pg_trgm_available():
    """Nhánh tìm kiếm dùng TrigramSimilarity — không có extension thì bỏ qua
    test đó, giống cách apps/vocabulary/tests.py đang làm."""
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM pg_extension WHERE extname = 'pg_trgm'")
        return cursor.fetchone()[0] > 0


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

    # --- Thanh lọc chủ đề nhiều-lựa-chọn (15/09/2026) ---------------------

    def _topic_word(self, slug, name, word, reading):
        topic, _ = Topic.objects.get_or_create(slug=slug, defaults={"name": name})
        vocab = Vocabulary.objects.create(word=word, reading=reading, meaning_vi=name)
        VocabularyTopic.objects.create(vocabulary=vocab, topic=topic)
        return topic, vocab

    def test_picker_filters_by_several_topics_at_once(self):
        """Chọn nhiều chủ đề = HOẶC, giống thanh lọc ở SC05."""
        self._topic_word("nha-hang", "Nhà hàng", "注文する", "ちゅうもんする")
        self._topic_word("hop-hanh", "Họp hành", "議事録", "ぎじろく")
        Vocabulary.objects.create(word="孤児", reading="こじ", meaning_vi="từ mồ côi")

        response = self.client.get(
            reverse("practice_sheets:create"), {"topic": ["nha-hang", "hop-hanh"]}
        )
        self.assertEqual(response.context["word_total"], 2)
        self.assertEqual(
            {t.slug for t in response.context["selected_topics"]}, {"nha-hang", "hop-hanh"}
        )
        self.assertNotContains(response, "こじ")

    def test_picker_does_not_count_a_word_twice(self):
        """Từ thuộc hai chủ đề đang chọn vẫn chỉ hiện một lần (.distinct())."""
        topic_a, vocab = self._topic_word("nha-hang", "Nhà hàng", "注文する", "ちゅうもんする")
        topic_b, _ = Topic.objects.get_or_create(slug="hop-hanh", defaults={"name": "Họp hành"})
        VocabularyTopic.objects.create(vocabulary=vocab, topic=topic_b)

        response = self.client.get(
            reverse("practice_sheets:create"), {"topic": ["nha-hang", "hop-hanh"]}
        )
        self.assertEqual(response.context["word_total"], 1)
        self.assertEqual(len(response.context["words"]), 1)

    def test_picker_filter_link_toggles(self):
        self._topic_word("nha-hang", "Nhà hàng", "注文する", "ちゅうもんする")
        self._topic_word("hop-hanh", "Họp hành", "議事録", "ぎじろく")

        response = self.client.get(reverse("practice_sheets:create"), {"topic": ["nha-hang"]})
        links = {f["topic"].slug: f for f in response.context["topic_filters"]}
        self.assertTrue(links["nha-hang"]["is_selected"])
        self.assertNotIn("topic=", links["nha-hang"]["query"])       # bấm lần 2 -> bỏ lọc
        self.assertIn("topic=nha-hang", links["hop-hanh"]["query"])  # cộng dồn
        self.assertIn("topic=hop-hanh", links["hop-hanh"]["query"])

    def test_picker_form_action_keeps_the_filter(self):
        """POST lỗi validate không được làm danh sách nhảy về 'tất cả chủ đề'."""
        self._topic_word("nha-hang", "Nhà hàng", "注文する", "ちゅうもんする")

        response = self.client.get(reverse("practice_sheets:create"), {"topic": ["nha-hang"]})
        self.assertEqual(
            response.context["picker_action"],
            reverse("practice_sheets:create") + "?topic=nha-hang",
        )

    def test_picker_topic_filter_is_a_searchable_dropdown(self):
        """Chủ đề nằm trong dropdown có checkbox + ô tìm nhanh (giống SC05).

        Trước 18/09/2026 là một dãy thẻ link — hơn trăm chủ đề trải kín màn hình.
        """
        self._topic_word("hop-hanh", "Họp hành", "議事録", "ぎじろく")

        response = self.client.get(reverse("practice_sheets:create"))
        self.assertContains(response, 'id="topic-filter-form"')
        self.assertContains(response, 'id="topic-dropdown"')
        self.assertContains(response, 'id="topic-search"')
        self.assertContains(response, 'data-search="Họp hành  hop-hanh"')
        self.assertContains(response, '<input type="checkbox" name="topic" value="hop-hanh">')
        # Không còn dãy thẻ link lọc chủ đề.
        self.assertNotContains(response, 'class="tag tag-filter')

    def test_picker_filters_by_keyword(self):
        """Ô "Tìm từ vựng" dùng chung selectors.filter_vocabulary với SC05."""
        if not _pg_trgm_available():
            self.skipTest("database đang chạy không có extension pg_trgm")
        self._topic_word("nha-hang", "Nhà hàng", "注文する", "ちゅうもんする")
        self._topic_word("hop-hanh", "Họp hành", "議事録", "ぎじろく")

        response = self.client.get(reverse("practice_sheets:create"), {"q": "ちゅうもん"})
        self.assertEqual(response.context["word_query"], "ちゅうもん")
        self.assertEqual(
            [w.word for w in response.context["words"]], ["注文する"]
        )

    def test_picker_form_action_keeps_the_keyword(self):
        self._topic_word("nha-hang", "Nhà hàng", "注文する", "ちゅうもんする")
        response = self.client.get(
            reverse("practice_sheets:create"), {"topic": "nha-hang", "q": "abc"}
        )
        self.assertIn("topic=nha-hang", response.context["picker_action"])
        self.assertIn("q=abc", response.context["picker_action"])

    def test_picker_ignores_unknown_topic_slug(self):
        Vocabulary.objects.create(word="予約", reading="よやく", meaning_vi="đặt chỗ")

        response = self.client.get(reverse("practice_sheets:create"), {"topic": "khong-ton-tai"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["selected_topics"], [])
        self.assertEqual(response.context["word_total"], 1)

    def test_font_error_shows_message_instead_of_500(self):
        vocab = Vocabulary.objects.create(
            word="予約", reading="よやく", meaning_vi="đặt chỗ",
        )
        with mock.patch(
            "apps.practice_sheets.views.generate_sheet_pdf",
            side_effect=pdf_generator.PracticeSheetFontError("thiếu font"),
        ):
            response = self.client.post(
                reverse("practice_sheets:create"),
                {"source": "existing", "sheet_type": "writing", "word_ids": [vocab.pk], "lines_per_word": 2},
                follow=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("practice_sheets.generate.error.font_missing"))
        # Không được tạo bản ghi rỗng khi PDF sinh hỏng.
        self.assertEqual(self.user.practice_sheets.count() if hasattr(self.user, "practice_sheets") else 0, 0)


# ---------------------------------------------------------------------------
# Đọc danh sách từ người dùng tải lên (14/09/2026)
# ---------------------------------------------------------------------------

class WordSourceTests(TestCase):
    def _csv(self, header, *rows):
        return dataio.write_csv(header, [list(r) for r in rows])

    def test_accepts_the_sc07b_column_names(self):
        items, skipped = wordsource.parse_word_file(
            self._csv(["word", "reading", "meaning_vi"], ["納品", "のうひん", "giao hàng"]),
            "x.csv",
        )
        self.assertEqual(skipped, 0)
        self.assertEqual(items[0], wordsource.WordItem("納品", "のうひん", "giao hàng"))

    def test_accepts_vietnamese_headers_with_or_without_accents(self):
        """Người tự gõ file sẽ viết 'Nghĩa tiếng Việt' hoặc 'Nghia tieng Viet' —
        bắt gõ đúng từng ký tự thì không ai nhập nổi."""
        for header in (
            ["Từ vựng", "Cách đọc", "Nghĩa tiếng Việt"],
            ["TU VUNG", "cach doc", "nghia tieng viet"],
            ["表記", "よみ", "意味"],
        ):
            items, _ = wordsource.parse_word_file(
                self._csv(header, ["出張", "しゅっちょう", "đi công tác"]), "x.csv"
            )
            self.assertEqual(items[0].meaning_vi, "đi công tác", header)

    def test_only_the_word_column_is_required(self):
        items, _ = wordsource.parse_word_file(self._csv(["word"], ["報告"]), "x.csv")
        self.assertEqual(items, [wordsource.WordItem("報告", "", "")])

    def test_file_without_a_word_column_is_refused(self):
        with self.assertRaises(dataio.DataFileError) as ctx:
            wordsource.parse_word_file(self._csv(["reading", "meaning_vi"], ["よみ", "nghĩa"]), "x.csv")
        self.assertEqual(ctx.exception.message_key, "practice_sheets.upload.error.missing_required_column")

    def test_blank_and_duplicate_rows_are_skipped_not_fatal(self):
        """Một dòng trống thừa không được làm hỏng cả lần in."""
        items, skipped = wordsource.parse_word_file(
            self._csv(
                ["word", "reading", "meaning_vi"],
                ["納品", "のうひん", "giao hàng"],
                ["", "", ""],
                ["納品", "のうひん", "giao hàng"],
                ["報告", "ほうこく", "báo cáo"],
            ),
            "x.csv",
        )
        self.assertEqual([i.word for i in items], ["納品", "報告"])
        self.assertEqual(skipped, 2)

    def test_too_many_words_is_refused(self):
        rows = [[f"語{i}", "", ""] for i in range(wordsource.MAX_WORDS_PER_SHEET + 1)]
        with self.assertRaises(dataio.DataFileError) as ctx:
            wordsource.parse_word_file(self._csv(["word", "reading", "meaning_vi"], *rows), "x.csv")
        self.assertEqual(ctx.exception.message_key, "practice_sheets.upload.error.too_many_words")

    def test_commas_inside_a_sentence_do_not_shift_columns(self):
        """CSV đi qua module csv nên ô có dấu phẩy được bọc nháy đúng chuẩn."""
        items, _ = wordsource.parse_word_file(
            self._csv(["word", "reading", "meaning_vi"],
                      ["打ち合わせ", "うちあわせ", "buổi họp, trao đổi công việc"]),
            "x.csv",
        )
        self.assertEqual(items[0].meaning_vi, "buổi họp, trao đổi công việc")


class GuideCharacterTests(TestCase):
    def test_guide_covers_the_whole_word_not_just_the_first_letter(self):
        """Bản đầu chỉ đổ chữ mờ cho word[0] vào đúng một ô — với 打ち合わせ thì
        người học chỉ được đồ mỗi chữ 打."""
        self.assertEqual(
            pdf_generator._guide_chars_for("打ち合わせ", True),
            ["打", "ち", "合", "わ", "せ"],
        )

    def test_no_guide_when_turned_off(self):
        self.assertEqual(pdf_generator._guide_chars_for("打ち合わせ", False), [])

    def test_guide_never_overflows_the_row(self):
        long_word = "あ" * 40
        self.assertEqual(
            len(pdf_generator._guide_chars_for(long_word, True)), pdf_generator.CELLS_PER_ROW
        )


class RecallPdfTests(TestCase):
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
        self.words = [
            wordsource.WordItem("納品", "のうひん", "giao hàng"),
            wordsource.WordItem("報告", "ほうこく", "báo cáo"),
            wordsource.WordItem("出張", "しゅっちょう", "đi công tác"),
        ]

    def _pages(self, content):
        data = content.read()
        self.assertTrue(data.startswith(b"%PDF"))
        return data.count(b"/Type /Page\n") or data.count(b"/Type /Page")

    def test_generates_a_real_pdf(self):
        filename, content = pdf_generator.generate_recall_pdf(self.words)
        self.assertEqual(filename, "phieu_on_tap.pdf")
        self.assertTrue(content.read().startswith(b"%PDF"))

    def test_answer_key_adds_a_page(self):
        _, without = pdf_generator.generate_recall_pdf(self.words, include_answer_key=False)
        _, with_key = pdf_generator.generate_recall_pdf(self.words, include_answer_key=True)
        self.assertGreater(len(with_key.read()), len(without.read()))

    def test_shuffle_with_a_seed_is_reproducible(self):
        """Cùng seed phải ra cùng thứ tự — nếu không thì trang đáp án và trang
        câu hỏi có thể lệch nhau."""
        a = pdf_generator.generate_recall_pdf(self.words, shuffle_order=True, seed=1)[1].read()
        b = pdf_generator.generate_recall_pdf(self.words, shuffle_order=True, seed=1)[1].read()
        self.assertEqual(len(a), len(b))

    def test_unknown_sheet_type_falls_back_instead_of_crashing(self):
        filename, _ = pdf_generator.generate_sheet_pdf("khong-co-that", self.words)
        self.assertEqual(filename, "phieu_luyen_viet.pdf")

    def test_dispatcher_routes_recall(self):
        filename, _ = pdf_generator.generate_sheet_pdf(
            SHEET_TYPE_RECALL, self.words, recall_direction=RECALL_VI_TO_JP
        )
        self.assertEqual(filename, "phieu_on_tap.pdf")


class SheetCreationTests(TestCase):
    """Luồng thật của SC10: chọn từ / tải file -> sinh PDF -> lưu bản ghi."""

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
        self.user = User.objects.create_user(username="dat", password="MatKhauRatManh123")
        self.client.force_login(self.user)
        self.url = reverse("practice_sheets:create")
        self.vocab = [
            Vocabulary.objects.create(word="納品", reading="のうひん", meaning_vi="giao hàng"),
            Vocabulary.objects.create(word="報告", reading="ほうこく", meaning_vi="báo cáo"),
        ]

    def test_writing_sheet_from_existing_words(self):
        response = self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_WRITING,
            "word_ids": [v.pk for v in self.vocab], "lines_per_word": 3,
            "show_guide_character": "on",
        })
        sheet = PracticeSheet.objects.get()
        self.assertRedirects(response, reverse("practice_sheets:download", args=[sheet.pk]))
        self.assertEqual(sheet.lines_per_word, 3)
        self.assertEqual(sheet.word_links.count(), 2)
        self.assertTrue(sheet.pdf_file.name.endswith(".pdf"))

    def test_link_rows_keep_their_audit_columns(self):
        """sheet.words.set() đi qua bulk_create nên bỏ qua save() và để trống
        created_by — phải create() từng dòng."""
        self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_WRITING,
            "word_ids": [self.vocab[0].pk],
        })
        link = PracticeSheetWord.objects.get()
        self.assertEqual(link.created_by, self.user)

    def test_selection_order_is_kept(self):
        """filter(id__in=...) trả theo thứ tự DB, không theo thứ tự người chọn."""
        response = self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_WRITING,
            "word_ids": [self.vocab[1].pk, self.vocab[0].pk],
        })
        sheet = PracticeSheet.objects.get()
        self.assertEqual(
            [i.word for i in sheet.word_items()],
            [self.vocab[1].word, self.vocab[0].word],
        )
        self.assertEqual(response.status_code, 302)

    def test_uploaded_words_are_printed_but_never_saved_to_the_dictionary(self):
        """Quyết định của Dat: người học in được danh sách riêng mà không làm
        bẩn bảng Vocabulary chung."""
        payload = dataio.write_csv(
            ["word", "reading", "meaning_vi"],
            [["請求書", "せいきゅうしょ", "hoá đơn"], ["出張", "しゅっちょう", "đi công tác"]],
        )
        upload = SimpleUploadedFile("cua_toi.csv", payload, content_type="text/csv")
        before = Vocabulary.objects.count()
        self.client.post(self.url, {
            "source": "upload", "sheet_type": SHEET_TYPE_WRITING, "word_file": upload,
        })
        self.assertEqual(Vocabulary.objects.count(), before)
        sheet = PracticeSheet.objects.get()
        self.assertEqual(sheet.word_links.count(), 0)
        self.assertEqual([w["word"] for w in sheet.custom_words], ["請求書", "出張"])
        self.assertEqual([i.word for i in sheet.word_items()], ["請求書", "出張"])

    def test_recall_sheet_needs_a_direction(self):
        """Hai hướng cho ra hai tờ giấy khác hẳn nhau nên không chọn hộ được."""
        response = self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_RECALL,
            "word_ids": [self.vocab[0].pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], None,
                             message("practice_sheets.validation.direction_required"))
        self.assertEqual(PracticeSheet.objects.count(), 0)

    def test_recall_sheet_stores_its_own_options(self):
        self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_RECALL,
            "direction_vi_jp": "on",
            "word_ids": [v.pk for v in self.vocab],
            "include_answer_key": "on", "shuffle_order": "on",
        })
        sheet = PracticeSheet.objects.get()
        self.assertEqual(sheet.sheet_type, SHEET_TYPE_RECALL)
        self.assertEqual(sheet.recall_direction, RECALL_VI_TO_JP)
        self.assertTrue(sheet.include_answer_key)
        self.assertTrue(sheet.shuffle_order)
        self.assertFalse(sheet.include_sentence_box)  # ô không tích -> False

    def test_no_words_selected_is_a_message_not_an_empty_sheet(self):
        response = self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_WRITING, "word_ids": [],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, message("practice_sheets.generate.error.no_words"))
        self.assertEqual(PracticeSheet.objects.count(), 0)

    def test_download_belongs_to_its_owner_only(self):
        self.client.post(self.url, {
            "source": "existing", "sheet_type": SHEET_TYPE_WRITING,
            "word_ids": [self.vocab[0].pk],
        })
        sheet = PracticeSheet.objects.get()
        self.assertEqual(self.client.get(
            reverse("practice_sheets:download", args=[sheet.pk])).status_code, 200)
        other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")
        self.client.force_login(other)
        self.assertEqual(self.client.get(
            reverse("practice_sheets:download", args=[sheet.pk])).status_code, 404)

    def test_template_download_matches_the_parser(self):
        """File mẫu tải về phải nạp lại được ngay — không thì nó vô dụng."""
        for fmt in ("csv", "xlsx"):
            payload = self.client.get(reverse("practice_sheets:template", args=[fmt])).content
            items, _ = wordsource.parse_word_file(payload, f"x.{fmt}")
            self.assertTrue(items, fmt)

    def test_screen_renders_without_template_leaks(self):
        from apps.core.tests import TEMPLATE_MARKERS

        html = self.client.get(self.url).content.decode()
        for marker in TEMPLATE_MARKERS:
            self.assertNotIn(marker, html, msg=f'màn SC10 còn sót "{marker}"')


class RecallDirectionCheckboxTests(TestCase):
    """Hai ô tick hướng (quyết định của Dat 14/09) thay cho ô radio ba trạng thái.

    Tick cả hai = trộn. DB vẫn lưu một chuỗi jp_vi/vi_jp/mixed như cũ nên không
    phải migration — phép quy đổi nằm ở PracticeSheetForm._direction_code().
    """

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
        self.user = User.objects.create_user(username="dat", password="MatKhauRatManh123")
        self.client.force_login(self.user)
        self.url = reverse("practice_sheets:create")
        self.vocab = Vocabulary.objects.create(
            word="納品", reading="のうひん", meaning_vi="giao hàng",
        )

    def _post(self, **ticks):
        payload = {
            "source": "existing", "sheet_type": SHEET_TYPE_RECALL,
            "word_ids": [self.vocab.pk],
        }
        payload.update({k: "on" for k, v in ticks.items() if v})
        return self.client.post(self.url, payload)

    def test_only_jp_vi(self):
        self._post(direction_jp_vi=True)
        self.assertEqual(PracticeSheet.objects.get().recall_direction, RECALL_JP_TO_VI)

    def test_only_vi_jp(self):
        self._post(direction_vi_jp=True)
        self.assertEqual(PracticeSheet.objects.get().recall_direction, RECALL_VI_TO_JP)

    def test_both_ticked_means_mixed(self):
        self._post(direction_jp_vi=True, direction_vi_jp=True)
        self.assertEqual(PracticeSheet.objects.get().recall_direction, RECALL_MIXED)

    def test_answer_key_is_independent_of_direction(self):
        self._post(direction_jp_vi=True)
        self.assertFalse(PracticeSheet.objects.get().include_answer_key)
        PracticeSheet.objects.all().delete()
        self._post(direction_jp_vi=True, include_answer_key=True)
        self.assertTrue(PracticeSheet.objects.get().include_answer_key)

    def test_answer_only_is_refused(self):
        """Chỉ tick Answer thì phiếu in ra không có chỗ trống nào để làm bài."""
        response = self._post(include_answer_key=True)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], None,
                             message("practice_sheets.validation.direction_required"))
        self.assertEqual(PracticeSheet.objects.count(), 0)

    def test_screen_opens_with_jp_vi_and_answer_ticked(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('name="direction_jp_vi" id="dirjp_a" checked', html)
        self.assertIn('name="direction_vi_jp" id="dirvi_a">', html)
        self.assertIn('name="include_answer_key" id="answers_a" checked', html)


class MixedDirectionBalanceTests(TestCase):
    def test_mixed_splits_roughly_in_half_instead_of_rolling_a_dice_per_word(self):
        """Bốc ngẫu nhiên từng từ thì 7 từ rất dễ ra 5 JP / 2 VN — phiếu lệch hẳn
        về một phía và mất tác dụng của việc trộn."""
        import random

        for count in (2, 7, 20, 21):
            plan = pdf_generator._direction_plan(count, RECALL_MIXED, random.Random(0))
            self.assertEqual(len(plan), count)
            jp = plan.count(RECALL_JP_TO_VI)
            self.assertLessEqual(abs(jp - (count - jp)), 1, f"{count} từ -> {plan}")

    def test_a_single_direction_is_used_for_every_word(self):
        import random

        plan = pdf_generator._direction_plan(5, RECALL_VI_TO_JP, random.Random(0))
        self.assertEqual(plan, [RECALL_VI_TO_JP] * 5)
