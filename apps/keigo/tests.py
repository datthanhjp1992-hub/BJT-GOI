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


# =============================================================================
# SC20-SC22 -- Bai tap kinh ngu
# =============================================================================
from apps.learning.models import StudySession  # noqa: E402

from . import exercises  # noqa: E402
from .models import (  # noqa: E402
    ExerciseSection, ExerciseSet, Question, QuestionOption, UserExerciseAttempt, UserQuestionAnswer,
)


class ExerciseTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.user = User.objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        cls.other = User.objects.create_user(username="nguoikhac", password="MatKhauRatManh123")

        # Bo 1: mot cau dien + mot cau sap xep ★
        cls.s1 = ExerciseSet.objects.create(title="BÀI TẬP 3", slug="bai-tap-3", display_order=1, question_count=2)
        sec = ExerciseSection.objects.create(exercise_set=cls.s1, number=1, display_order=1,
                                             instruction_jp="問題 次の__★__に入れるのに最もよいものを選びなさい。")
        cls.q_mcq = Question.objects.create(code="bt03-q01", section=sec, number=1, question_type="mcq_blank",
                                            stem_jp="ご用が____、わたくしに<b>おっしゃって</b>ください。")
        cls.mcq_ok = QuestionOption.objects.create(question=cls.q_mcq, position=1, text_jp="おありでしたら", is_correct=True)
        cls.mcq_ng = QuestionOption.objects.create(question=cls.q_mcq, position=2, text_jp="いらっしゃったら")
        cls.q_ord = Question.objects.create(code="bt03-q02", section=sec, number=2, question_type="ordering",
                                            stem_jp="建物の前に____ ____ __★__ ____いたします。",
                                            star_position=3, correct_order="1234")
        cls.ord_opts = [QuestionOption.objects.create(question=cls.q_ord, position=i, text_jp=t, is_correct=(i == 3))
                        for i, t in enumerate(["車を", "とめない", "ように", "お願い"], start=1)]

        # Bo 2: doan van cloze, hai cho trong
        cls.s2 = ExerciseSet.objects.create(title="BÀI TẬP 12", slug="bai-tap-12", display_order=2, question_count=2)
        sec2 = ExerciseSection.objects.create(
            exercise_set=cls.s2, number=2, display_order=2,
            instruction_jp="問題2 次の文章を読んで、（11）から（12）の中に入る最もよいものを選びなさい。",
            passage_jp="恩師のお宅へ年始に（11）の帰り、電車に乗った。\nおばあさんは髪を結んでいる。（12）腰が少し曲がっている。")
        cls.q11 = Question.objects.create(code="bt12-q11", section=sec2, number=11, question_type="cloze", stem_jp="(11)")
        cls.q11_ok = QuestionOption.objects.create(question=cls.q11, position=1, text_jp="うかがって", is_correct=True)
        cls.q11_ng = QuestionOption.objects.create(question=cls.q11, position=2, text_jp="拝見して")
        cls.q12 = Question.objects.create(code="bt12-q12", section=sec2, number=12, question_type="cloze", stem_jp="(12)")
        cls.q12_ok = QuestionOption.objects.create(question=cls.q12, position=1, text_jp="小柄なうえに", is_correct=True)
        QuestionOption.objects.create(question=cls.q12, position=2, text_jp="小柄なわりに")

    def setUp(self):
        self.client.force_login(self.user)

    def play(self, s):
        return reverse("keigo:bai_tap_lam", args=[s.slug])

    def start(self, s):
        return self.client.post(reverse("keigo:bai_tap_bat_dau", args=[s.slug]))

    def answer(self, s, q, opt):
        return self.client.post(self.play(s), {"question": q.pk, "option": opt.pk})

    def finish(self, s):
        return self.client.post(reverse("keigo:bai_tap_nop", args=[s.slug]))

    def do_set1(self, correct_mcq=True, correct_ord=True):
        self.start(self.s1)
        self.answer(self.s1, self.q_mcq, self.mcq_ok if correct_mcq else self.mcq_ng)
        self.answer(self.s1, self.q_ord, self.ord_opts[2] if correct_ord else self.ord_opts[0])
        return self.finish(self.s1)


class ExerciseListTests(ExerciseTestCase):
    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        url = reverse("keigo:bai_tap")
        self.assertRedirects(self.client.get(url), reverse("accounts:login") + "?next=" + url)

    def test_route_not_shadowed_by_lesson_slug(self):
        r = self.client.get(reverse("keigo:bai_tap"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "keigo/bai_tap.html")

    def test_sidebar_link_is_real_and_active(self):
        r = self.client.get(reverse("keigo:bai_tap"))
        self.assertContains(r, f'href="{reverse("keigo:bai_tap")}"')
        self.assertNotContains(r, "sidenav-sublink is-soon")

    def test_rows_show_type_chips_and_new_user_tip(self):
        r = self.client.get(reverse("keigo:bai_tap"))
        rows = r.context["rows"]
        self.assertEqual([x.question_total for x in rows], [2, 2])
        self.assertEqual([c.code for c in rows[0].chips], ["mcq_blank", "ordering"])
        self.assertTrue(r.context["is_new"])
        self.assertIsNone(r.context["resume"])

    def test_best_score_and_tabs(self):
        self.do_set1(correct_mcq=False)
        self.do_set1()
        r = self.client.get(reverse("keigo:bai_tap"))
        row = r.context["rows"][0]
        self.assertEqual((row.attempt_count, row.best_score, row.best_total), (2, 2, 2))
        done = self.client.get(reverse("keigo:bai_tap") + "?view=da").context["rows"]
        todo = self.client.get(reverse("keigo:bai_tap") + "?view=chua").context["rows"]
        self.assertEqual([x.exercise_set for x in done], [self.s1])
        self.assertEqual([x.exercise_set for x in todo], [self.s2])

    def test_unknown_view_falls_back_to_all(self):
        r = self.client.get(reverse("keigo:bai_tap") + "?view=xyz")
        self.assertEqual(r.context["view"], "all")
        self.assertEqual(len(r.context["rows"]), 2)


class ExerciseStartTests(ExerciseTestCase):
    def test_start_must_be_post(self):
        r = self.client.get(reverse("keigo:bai_tap_bat_dau", args=[self.s1.slug]))
        self.assertEqual(r.status_code, 405)
        self.assertFalse(UserExerciseAttempt.objects.exists())

    def test_start_creates_attempt_once(self):
        self.assertRedirects(self.start(self.s1), self.play(self.s1))
        self.start(self.s1)
        attempt = UserExerciseAttempt.objects.get()
        self.assertEqual(attempt.total, 2)
        self.assertIsNone(attempt.finished_at)

    def test_play_without_attempt_goes_back_to_list(self):
        self.assertRedirects(self.client.get(self.play(self.s1)), reverse("keigo:bai_tap"))

    def test_abandon_deletes_open_attempt(self):
        self.start(self.s1)
        self.answer(self.s1, self.q_mcq, self.mcq_ok)
        self.client.post(reverse("keigo:bai_tap_bo", args=[self.s1.slug]))
        self.assertFalse(UserExerciseAttempt.objects.exists())
        self.assertFalse(UserQuestionAnswer.objects.exists())

    def test_list_shows_resume_card(self):
        self.start(self.s2)
        r = self.client.get(reverse("keigo:bai_tap"))
        self.assertEqual(r.context["resume"].exercise_set, self.s2)


class ExercisePlayTests(ExerciseTestCase):
    def setUp(self):
        super().setUp()
        self.start(self.s1)

    def test_first_question_escapes_stem(self):
        r = self.client.get(self.play(self.s1))
        self.assertEqual(r.context["question"], self.q_mcq)
        self.assertContains(r, "&lt;b&gt;おっしゃって&lt;/b&gt;")
        self.assertContains(r, '<span class="blank is-cur">？</span>')

    def test_answer_redirects_to_feedback_and_scores(self):
        r = self.answer(self.s1, self.q_mcq, self.mcq_ok)
        self.assertRedirects(r, f"{self.play(self.s1)}?da={self.q_mcq.pk}")
        attempt = UserExerciseAttempt.objects.get()
        self.assertEqual(attempt.score, 1)
        page = self.client.get(r["Location"])
        self.assertTrue(page.context["answer"].is_correct)
        self.assertContains(page, '<span class="blank is-ok">おありでしたら</span>')

    def test_second_answer_does_not_overwrite_first(self):
        self.answer(self.s1, self.q_mcq, self.mcq_ng)
        self.answer(self.s1, self.q_mcq, self.mcq_ok)
        a = UserQuestionAnswer.objects.get()
        self.assertEqual(a.selected_option, self.mcq_ng)
        self.assertEqual(UserExerciseAttempt.objects.get().score, 0)

    def test_missing_or_foreign_option_is_rejected(self):
        self.client.post(self.play(self.s1), {"question": self.q_mcq.pk})
        self.client.post(self.play(self.s1), {"question": self.q_mcq.pk, "option": self.ord_opts[0].pk})
        self.assertFalse(UserQuestionAnswer.objects.exists())

    def test_question_of_other_set_is_ignored(self):
        self.client.post(self.play(self.s1), {"question": self.q11.pk, "option": self.q11_ok.pk})
        self.assertFalse(UserQuestionAnswer.objects.exists())

    def test_ordering_feedback_shows_full_sentence(self):
        self.answer(self.s1, self.q_mcq, self.mcq_ok)
        r = self.client.get(self.play(self.s1))
        self.assertTrue(r.context["is_ordering"])
        self.assertContains(r, '<span class="slot is-star">★</span>')
        r = self.client.get(self.answer(self.s1, self.q_ord, self.ord_opts[0])["Location"])
        self.assertContains(r, '<span class="slot is-filled is-star">ように<sup>3</sup></span>')
        self.assertTrue(r.context["is_last"])
        self.assertContains(r, reverse("keigo:bai_tap_nop", args=[self.s1.slug]))

    def test_feedback_param_for_unanswered_question_is_ignored(self):
        r = self.client.get(f"{self.play(self.s1)}?da={self.q_ord.pk}")
        self.assertEqual(r.context["question"], self.q_mcq)
        self.assertIsNone(r.context["answer"])


class ExercisePassageTests(ExerciseTestCase):
    def test_current_blank_highlighted_and_answered_blank_filled(self):
        self.start(self.s2)
        r = self.client.get(self.play(self.s2))
        self.assertContains(r, '<span class="blank is-cur">（11）</span>')
        # instruction 「（11）から（12）」 KHONG bi doi thanh cho trong
        self.assertEqual(r.context["instruction_html"].count("blank"), 0)
        self.answer(self.s2, self.q11, self.q11_ng)
        r = self.client.get(self.play(self.s2))
        self.assertEqual(r.context["question"], self.q12)
        self.assertIn('<span class="blank is-ng">拝見して</span>', r.context["passage_html"])
        self.assertIn('<span class="blank is-cur">（12）</span>', r.context["passage_html"])

    def test_cloze_sentence_is_cut_from_passage(self):
        self.assertEqual(exercises.question_sentence(self.q12), "（12）腰が少し曲がっている。")


class ExerciseFinishAndResultTests(ExerciseTestCase):
    def test_cannot_finish_before_all_answered(self):
        self.start(self.s1)
        self.answer(self.s1, self.q_mcq, self.mcq_ok)
        self.assertRedirects(self.finish(self.s1), self.play(self.s1))
        self.assertIsNone(UserExerciseAttempt.objects.get().finished_at)

    def test_finish_writes_study_session_and_shows_result(self):
        r = self.do_set1(correct_ord=False)
        attempt = UserExerciseAttempt.objects.get()
        self.assertIsNotNone(attempt.finished_at)
        self.assertEqual(attempt.score, 1)
        session = StudySession.objects.get()
        self.assertEqual((session.session_type, session.words_reviewed, session.correct_answers), ("keigo", 2, 1))
        page = self.client.get(r["Location"])
        self.assertEqual(page.context["wrong_count"], 1)
        self.assertEqual([it.question for it in page.context["items"]], [self.q_ord])
        self.assertIsNone(page.context["best_before"])
        self.assertEqual(page.context["next_set"], self.s2)

    def test_record_badge_and_perfect_score(self):
        self.do_set1(correct_mcq=False)
        self.do_set1()
        r = self.client.get(reverse("keigo:bai_tap_ket_qua", args=[self.s1.slug]))
        self.assertTrue(r.context["is_record"])
        self.assertEqual(r.context["attempt_number"], 2)
        self.assertContains(r, "満点")

    def test_all_tab_lists_every_question(self):
        self.do_set1()
        r = self.client.get(reverse("keigo:bai_tap_ket_qua", args=[self.s1.slug]) + "?view=tat-ca")
        self.assertEqual(len(r.context["items"]), 2)

    def test_other_users_attempt_is_404(self):
        self.do_set1()
        attempt = UserExerciseAttempt.objects.get()
        self.client.force_login(self.other)
        url = reverse("keigo:bai_tap_ket_qua", args=[self.s1.slug]) + f"?lan={attempt.pk}"
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_result_without_finished_attempt_goes_to_list(self):
        self.assertRedirects(self.client.get(reverse("keigo:bai_tap_ket_qua", args=[self.s1.slug])),
                             reverse("keigo:bai_tap"))

    def test_index_links_to_exercises(self):
        self.assertContains(self.client.get(reverse("keigo:index")), f'href="{reverse("keigo:bai_tap")}"')
