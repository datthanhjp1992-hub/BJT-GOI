"""
Test cho app keigo -- SC17 (trang bai hoc).

Chay: python manage.py test apps.keigo
"""
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import selectors
from .models import KeigoExample, KeigoForm, KeigoLesson, KeigoPattern, KeigoPhrasePair, KeigoVerb

User = get_user_model()


class LessonTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.user = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")

        cls.ch1 = KeigoLesson.objects.create(title="TÔN KÍNH NGỮ", slug="ton-kinh-ngu",
                                             style_code="sonkei", display_order=1)
        cls.ch3 = KeigoLesson.objects.create(title="THẾ LỊCH SỰ", slug="the-lich-su",
                                             style_code="teinei", display_order=3)
        cls.ch5 = KeigoLesson.objects.create(title="BẢNG CHIA", slug="bang-chia-dong-tu-bat-quy-tac",
                                             display_order=5)
        cls.ch7 = KeigoLesson.objects.create(title="THAM KHẢO", slug="tham-khao", display_order=7)

        iu = KeigoVerb.objects.create(plain_form="言う", meaning_vi="nói", display_order=2)
        KeigoForm.objects.create(verb=iu, style_code="sonkei", form="おっしゃる", is_irregular=True)
        KeigoForm.objects.create(verb=iu, style_code="kenjo1", form="申し上げる", is_irregular=True)

        cls.p1 = KeigoPattern.objects.create(code="sonkei-o-go-da", lesson=cls.ch1, style_code="sonkei",
                                             title="お・ご～だ", formation="お/ご+N+だ", display_order=1)
        cls.p2 = KeigoPattern.objects.create(code="sonkei-agaru", lesson=cls.ch1, style_code="sonkei",
                                             title="～あがる", display_order=2)
        KeigoExample.objects.create(pattern=cls.p1, sentence_jp="{僭越|せんえつ}ながら", display_order=1)
        KeigoExample.objects.create(pattern=cls.p2, sentence_jp="どうぞ。", display_order=1)
        KeigoExample.objects.create(pattern=cls.p2, sentence_jp="おじゃまします。", speaker="A",
                                    pair_group=1, display_order=2)
        KeigoExample.objects.create(pattern=cls.p2, sentence_jp="お上がり下さい。", speaker="B",
                                    pair_group=1, display_order=3)

        KeigoPhrasePair.objects.create(lesson=cls.ch3, pair_type="adj_gozai", casual="安い",
                                       polite="安うございます", display_order=1)
        KeigoPhrasePair.objects.create(lesson=cls.ch7, pair_type="wrong", casual="おられますか",
                                       polite="いらっしゃいますか", display_order=1)
        KeigoPhrasePair.objects.create(lesson=cls.ch7, pair_type="cushion", polite="恐れ入りますが",
                                       group_label="依頼", display_order=1)

    def setUp(self):
        self.client.force_login(self.user)

    def url(self, lesson, key=None):
        base = reverse("keigo:lesson", args=[lesson.slug])
        return f"{base}?muc={key}" if key else base


class AccessTests(LessonTestCase):
    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        url = self.url(self.ch1)
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_unknown_slug_is_404(self):
        self.assertEqual(self.client.get(reverse("keigo:lesson", args=["khong-co"])).status_code, 404)

    def test_verb_table_chapter_redirects_to_sc18(self):
        self.assertRedirects(self.client.get(self.url(self.ch5)), reverse("keigo:tra_cuu"))

    def test_sidebar_learn_link_goes_to_first_chapter(self):
        self.assertRedirects(self.client.get(reverse("keigo:hoc")), self.url(self.ch1))

    def test_existing_routes_not_shadowed_by_slug(self):
        self.assertEqual(self.client.get(reverse("keigo:tra_cuu")).status_code, 200)


class ItemTests(LessonTestCase):
    def test_chapter1_items_irregular_first_then_patterns(self):
        keys = [i.key for i in selectors.lesson_items(self.ch1)]
        self.assertEqual(keys, [selectors.ITEM_IRREGULAR, "sonkei-o-go-da", "sonkei-agaru"])

    def test_default_item_is_irregular_table_of_this_style_only(self):
        resp = self.client.get(self.url(self.ch1))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "おっしゃる")
        self.assertNotContains(resp, "申し上げる")  # kenjo1 thuoc chuong 2

    def test_unknown_item_key_falls_back_to_first(self):
        resp = self.client.get(self.url(self.ch1, "khong-co"))
        self.assertEqual(resp.context["current"].key, selectors.ITEM_IRREGULAR)

    def test_pattern_item_renders_ruby_and_dialog(self):
        resp = self.client.get(self.url(self.ch1, "sonkei-agaru"))
        blocks = resp.context["current"].detail["blocks"]
        self.assertEqual([b["kind"] for b in blocks], ["sentence", "dialog"])
        self.assertEqual(len(blocks[1]["lines"]), 2)
        self.assertContains(resp, 'class="spk">A<')

        resp = self.client.get(self.url(self.ch1, "sonkei-o-go-da"))
        self.assertContains(resp, "<ruby>僭越<rt>せんえつ</rt></ruby>", html=False)

    def test_last_item_links_to_next_chapter(self):
        resp = self.client.get(self.url(self.ch1, "sonkei-agaru"))
        self.assertIsNone(resp.context["next_item"])
        self.assertContains(resp, f'href="{self.url(self.ch3)}"')

    def test_pair_items_wrong_and_plain(self):
        resp = self.client.get(self.url(self.ch3))
        self.assertFalse(resp.context["current"].detail["is_wrong_type"])
        self.assertContains(resp, "安うございます")

        keys = [i.key for i in selectors.lesson_items(self.ch7)]
        self.assertIn("cap-wrong", keys)
        self.assertIn("cap-cushion", keys)
        resp = self.client.get(self.url(self.ch7, "cap-wrong"))
        self.assertTrue(resp.context["current"].detail["is_wrong_type"])
        self.assertContains(resp, 'class="kl-xo"')

    def test_index_cards_link_to_lessons(self):
        resp = self.client.get(reverse("keigo:index"))
        self.assertContains(resp, f'href="{self.url(self.ch1)}"')


class LessonPdfTests(LessonTestCase):
    def pdf_url(self, lesson):
        return reverse("keigo:lesson_pdf", args=[lesson.slug])

    def test_lesson_page_has_print_button(self):
        resp = self.client.get(self.url(self.ch1))
        self.assertContains(resp, f'href="{self.pdf_url(self.ch1)}"')

    def test_pdf_contains_whole_chapter_not_only_current_item(self):
        resp = self.client.get(self.pdf_url(self.ch1))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn('filename="kinh-ngu-chuong-1-ton-kinh-ngu.pdf"', resp["Content-Disposition"])
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_every_block_type_renders(self):
        for lesson in (self.ch1, self.ch3, self.ch7):
            with self.subTest(lesson=lesson.slug):
                self.assertEqual(self.client.get(self.pdf_url(lesson)).status_code, 200)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        url = self.pdf_url(self.ch1)
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_verb_table_chapter_redirects_to_sc18(self):
        self.assertRedirects(self.client.get(self.pdf_url(self.ch5)), reverse("keigo:tra_cuu"))

    def test_missing_font_only_breaks_this_button(self):
        from unittest import mock

        from . import pdf as keigo_pdf
        with mock.patch.object(keigo_pdf, "_font_dirs", return_value=[]), \
                mock.patch.object(keigo_pdf.pdfmetrics, "getRegisteredFontNames", return_value=[]):
            resp = self.client.get(self.pdf_url(self.ch1))
        self.assertRedirects(resp, self.url(self.ch1))

    def test_mixed_text_is_split_by_font(self):
        from . import pdf as keigo_pdf
        markup = keigo_pdf._mk("Công thức {僭越|せんえつ}")
        self.assertIn(f'<font name="{keigo_pdf.FONT_VI}">Công thức </font>', markup)
        self.assertIn(f'<font name="{keigo_pdf.FONT_JP}">僭越</font>', markup)
        self.assertIn("せんえつ", markup)
        self.assertIn("&lt;b&gt;", keigo_pdf._runs("<b>"))  # escape, khong de lot markup


class PitfallTests(LessonTestCase):
    """SC19 -- Loi thuong gap. Dung lai du lieu LessonTestCase (adj_gozai o
    chuong 3, wrong + cushion o chuong 7) + them double / teinei."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # double #1-#2: cung group_label + cung casual -> 1 × voi 2 ○
        for order, polite in enumerate(["資料をお読みになりましたか。", "資料を読まれましたか。"], start=1):
            KeigoPhrasePair.objects.create(lesson=cls.ch7, pair_type="double", group_label="お読みになられる",
                                           casual="資料をお読みになられましたか。", polite=polite,
                                           display_order=order)
        KeigoPhrasePair.objects.create(lesson=cls.ch3, pair_type="teinei", polite="後ろに「です」「ます」を付ける",
                                       display_order=1)
        KeigoPhrasePair.objects.create(lesson=cls.ch3, pair_type="teinei", casual="です", polite="でございます",
                                       display_order=2)

    def get(self, **params):
        return self.client.get(reverse("keigo:loi_thuong_gap"), params)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        url = reverse("keigo:loi_thuong_gap")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_route_not_shadowed_by_lesson_slug(self):
        resp = self.get()
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "keigo/loi_thuong_gap.html")

    def test_default_tab_is_wrong_and_unknown_view_falls_back(self):
        self.assertEqual(self.get().context["view"], "wrong")
        self.assertEqual(self.get(view="khong-co").context["view"], "wrong")
        resp = self.get()
        self.assertEqual([t.code for t in resp.context["shown"]], ["wrong"])
        self.assertContains(resp, "いらっしゃいますか")
        self.assertNotContains(resp, "安うございます")  # nhom khac khong render

    def test_only_types_with_data_and_three_clusters(self):
        resp = self.get()
        self.assertEqual({t.code for t in resp.context["types"]},
                         {"wrong", "double", "adj_gozai", "teinei", "cushion"})
        self.assertEqual([k for k, _ in resp.context["clusters"]],
                         [selectors.PITFALL_KIND_XO, selectors.PITFALL_KIND_CONV, selectors.PITFALL_KIND_CUSHION])
        self.assertEqual(resp.context["total"], 7)
        self.assertEqual(resp.context["lesson_count"], 2)

    def test_link_back_to_lesson_item(self):
        resp = self.get(view="adj_gozai")
        self.assertContains(resp, f'href="{self.url(self.ch3, "cap-adj_gozai")}"')

    def test_double_same_casual_merged_into_one_x(self):
        t = self.get(view="double").context["shown"][0]
        self.assertEqual(len(t.groups), 1)
        self.assertEqual(t.groups[0]["label"], "お読みになられる")
        self.assertEqual(len(t.groups[0]["items"]), 1)
        self.assertEqual(len(t.groups[0]["items"][0]["answers"]), 2)

    def test_teinei_rule_row_is_heading_not_pair(self):
        resp = self.get(view="teinei")
        self.assertContains(resp, '<tr class="lt-rule"><td colspan="3"><span class="jp">後ろに「です」「ます」を付ける',
                            html=False)
        self.assertContains(resp, 'data-l="Thường">です')

    def test_check_mode_hides_polite_side_except_cushion(self):
        self.assertNotContains(self.get(), "lt-reveal")
        resp = self.get(an="1")
        self.assertContains(resp, 'class="lt-reveal"')
        self.assertTrue(resp.context["check"])
        # tab + nut bo tu kiem tra giu/doi ?an dung
        self.assertContains(resp, "view=double&amp;an=1")
        self.assertNotIn("an=1", resp.context["check_toggle_url"])

        resp = self.get(view="cushion", an="1")
        self.assertNotContains(resp, 'class="lt-reveal"')
        self.assertContains(resp, 'class="lt-nocheck')

    def test_search_spans_all_types_and_ignores_view(self):
        resp = self.get(view="wrong", q="ございます")
        codes = [t.code for t in resp.context["shown"]]
        self.assertEqual(codes, ["teinei", "adj_gozai"])  # thu tu theo sort_order MasterCode
        self.assertEqual(resp.context["match_total"], 2)
        self.assertNotContains(resp, "いらっしゃいますか")
        self.assertNotContains(resp, "後ろに")  # dong quy tac khong khop thi an

    def test_search_without_result_shows_empty_state(self):
        resp = self.get(q="ぴかちゅう")
        self.assertEqual(resp.context["shown"], [])
        self.assertContains(resp, "見つかりません")

    def test_sidebar_link_is_live_and_active(self):
        resp = self.get()
        self.assertContains(resp, f'href="{reverse("keigo:loi_thuong_gap")}"')
        self.assertEqual(resp.context["active_sub"], "loi_thuong_gap")
