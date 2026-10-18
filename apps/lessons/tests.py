import random
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse, reverse_lazy

from apps.core import dataio
from apps.core.constants import (
    PRACTICE_KIND_BLANK, PRACTICE_KIND_DRILL, PRACTICE_KIND_POLITE, politeness_level_choices, practice_kind_choices,
)

from . import services, views
from .models import (
    Drill, DrillItem, Lesson, PolitenessPhrase, Roleplay, RoleplayBlank, RoleplayLine, Unit, UserPracticeMark,
)


class LessonModelTests(TestCase):
    """T1 — docs/SPEC_LUYEN_TAP_BAI.md."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        cls.unit = Unit.objects.create(number=1, name_jp="紹介", name_vi="Giới thiệu")
        cls.lesson = Lesson.objects.create(unit=cls.unit, scene_no=2, title_jp="よろしくお願いします")
        cls.drill = Drill.objects.create(lesson=cls.lesson, example_prompt_jp="山川物産、佐藤課長",
                                         example_answer_jp="こちら、山川物産の佐藤課長です。")
        cls.roleplay = Roleplay.objects.create(unit=cls.unit, number=1, situation_vi="Tự giới thiệu.")

    def assertDuplicateRejected(self, model, **fields):
        with self.assertRaises(IntegrityError), transaction.atomic():
            model.objects.create(**fields)

    def test_natural_keys_reject_duplicates(self):
        DrillItem.objects.create(drill=self.drill, number=1, prompt_jp="a", answer_jp="b")
        self.assertDuplicateRejected(DrillItem, drill=self.drill, number=1, prompt_jp="c", answer_jp="d")
        self.assertDuplicateRejected(Drill, lesson=self.lesson, example_prompt_jp="x", example_answer_jp="y")
        RoleplayBlank.objects.create(roleplay=self.roleplay, number=1, answer_jp="申します")
        self.assertDuplicateRejected(RoleplayBlank, roleplay=self.roleplay, number=1, answer_jp="x")
        PolitenessPhrase.objects.create(lesson=self.lesson, phrase_jp="ヤンと申します", level_code="1")
        self.assertDuplicateRejected(PolitenessPhrase, lesson=self.lesson, phrase_jp="ヤンと申します", level_code="2")

    def test_mastercode_seeded(self):
        self.assertEqual([c for c, _ in politeness_level_choices()], ["1", "2", "3"])
        self.assertEqual([c for c, _ in practice_kind_choices()], ["drill", "blank", "polite"])

    def test_every_model_has_audit_columns(self):
        for model in dataio.importable_models():
            if model._meta.app_label != "lessons":
                continue
            names = {f.name for f in model._meta.get_fields()}
            self.assertTrue(set(dataio.AUDIT_FIELDS) <= names, model)

    def test_import_columns_use_natural_keys(self):
        """Header CSV ở docs/data/lessons/ (T2) phụ thuộc thẳng vào đây."""
        self.assertEqual(dataio.headers_for(Lesson)[:2], ["unit__number", "scene_no"])
        self.assertEqual(dataio.headers_for(DrillItem)[:2], ["drill__lesson__scene_no", "number"])
        self.assertEqual(dataio.headers_for(RoleplayBlank)[:3], ["roleplay__unit__number", "roleplay__number", "number"])
        order = [dataio.model_label(m) for m in dataio.importable_models()]
        self.assertLess(order.index("lessons.unit"), order.index("lessons.lesson"))
        self.assertLess(order.index("lessons.drill"), order.index("lessons.drillitem"))


class CheckLessonDataTests(TestCase):
    """T2 — check_lesson_data bắt được dữ liệu lệch, không chỉ in "đạt"."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_mastercode", verbosity=0)
        unit = Unit.objects.create(number=1, name_jp="紹介")
        lesson = Lesson.objects.create(unit=unit, scene_no=1, title_jp="はじめまして")
        drill = Drill.objects.create(lesson=lesson, example_prompt_jp="a", example_answer_jp="b")
        for n in (1, 2, 3):
            DrillItem.objects.create(drill=drill, number=n, prompt_jp=f"p{n}", answer_jp=f"a{n}")
        for number in (1, 2):
            rp = Roleplay.objects.create(unit=unit, number=number, situation_vi="x")
            RoleplayLine.objects.create(roleplay=rp, number=1, speaker="A", text_jp="スミスです。{1}。")
            RoleplayBlank.objects.create(roleplay=rp, number=1, answer_jp="よろしくお願いします")
        PolitenessPhrase.objects.create(lesson=lesson, phrase_jp="ヤンと申します", level_code="1")
        PolitenessPhrase.objects.create(lesson=lesson, phrase_jp="ヤンといいます", level_code="2")
        cls.roleplay = rp

    def run_check(self):
        out = StringIO()
        try:
            call_command("check_lesson_data", "--no-expected", stdout=out)
        except SystemExit:
            return False, out.getvalue()
        return True, out.getvalue()

    def test_consistent_data_passes(self):
        ok, out = self.run_check()
        self.assertTrue(ok, out)

    def test_blank_without_answer_fails(self):
        RoleplayLine.objects.create(roleplay=self.roleplay, number=2, speaker="B", text_jp="{2}。")
        ok, out = self.run_check()
        self.assertFalse(ok)
        self.assertIn("lời thoại có [1, 2], đáp án có [1]", out)

    def test_short_drill_fails(self):
        DrillItem.objects.filter(number=3).delete()
        self.assertFalse(self.run_check()[0])


class PracticeViewTestCase(TestCase):
    """Dữ liệu chung cho L1/L4: 2 chương, 12 bài có cặp lịch sự (chương 1: bài 1-6, chương 5: bài 7-12)."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        call_command("seed_mastercode", verbosity=0)
        cls.user = get_user_model().objects.create_user(username="nguoihoc", password="MatKhauRatManh123")
        cls.u1 = Unit.objects.create(number=1, name_jp="紹介する", name_vi="Giới thiệu")
        cls.u5 = Unit.objects.create(number=5, name_jp="依頼する", name_vi="Nhờ vả")
        cls.lessons = []
        for n in range(1, 13):
            lesson = Lesson.objects.create(unit=cls.u1 if n <= 6 else cls.u5, scene_no=n, title_jp=f"課{n}",
                                           title_vi=f"Bài {n}")
            PolitenessPhrase.objects.create(lesson=lesson, phrase_jp=f"丁寧{n}でございます", level_code="1")
            PolitenessPhrase.objects.create(lesson=lesson, phrase_jp=f"普通{n}だよ", level_code="3")
            cls.lessons.append(lesson)
        Roleplay.objects.create(unit=cls.u1, number=1, situation_vi="x")

    def setUp(self):
        self.client.force_login(self.user)


class PoliteServiceTests(PracticeViewTestCase):
    def test_pairs_skip_lessons_without_two_levels(self):
        odd = Lesson.objects.create(unit=self.u1, scene_no=40, title_jp="x")
        PolitenessPhrase.objects.create(lesson=odd, phrase_jp="一つだけ", level_code="2")
        found = services.pairs()
        self.assertNotIn(odd.id, found)
        formal, casual = found[self.lessons[0].id]
        self.assertEqual((formal.level_code, casual.level_code), ("1", "3"))

    def test_round_puts_wrong_pairs_first_then_unseen(self):
        wrong, right = self.lessons[3], self.lessons[4]
        services.record(self.user, PRACTICE_KIND_POLITE, services.pairs([wrong])[wrong.id][0].id, False)
        for lesson in self.lessons[:11]:
            if lesson != wrong:
                services.record(self.user, PRACTICE_KIND_POLITE, services.pairs([lesson])[lesson.id][0].id, True)
        state = services.build_round(self.user, "all", rng=random.Random(1))
        self.assertEqual(len(state["ids"]), services.ROUND_SIZE)
        self.assertEqual(state["ids"][0], wrong.id)            # đang sai -> hỏi trước
        self.assertEqual(state["ids"][1], self.lessons[11].id)  # chưa làm -> kế tiếp
        self.assertNotIn(right.id, state["ids"][:2])

    def test_round_respects_unit_group(self):
        state = services.build_round(self.user, "5-8")
        self.assertEqual(set(state["ids"]), {l.id for l in self.lessons[6:]})


class PoliteViewTests(PracticeViewTestCase):
    url = reverse_lazy("lessons:polite")

    def answer(self, i, formal):
        state = self.client.session[views.SESSION_KEY]
        q = services.round_question(state, i)
        option = q["formal"] if formal else q["casual"]
        return self.client.post(reverse("lessons:polite_answer"), {"i": i, "option": option.id}), q

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.get(reverse("lessons:index")).status_code, 302)

    def test_correct_answer_marks_known_and_refresh_does_not_rescore(self):
        self.client.get(self.url)
        resp, q = self.answer(1, formal=True)
        self.assertRedirects(resp, f"{self.url}?chuong=all&i=1")
        mark = UserPracticeMark.objects.get(user=self.user, kind=PRACTICE_KIND_POLITE, object_id=q["formal"].id)
        self.assertEqual((mark.is_known, mark.times), (True, 1))
        self.answer(1, formal=False)  # gửi lại cùng câu: không chấm lại
        mark.refresh_from_db()
        self.assertEqual((mark.is_known, mark.times), (True, 1))
        page = self.client.get(f"{self.url}?chuong=all&i=1")
        self.assertTrue(page.context["answered"])
        self.assertContains(page, q["formal"].phrase_jp)

    def test_wrong_answer_and_result_page(self):
        self.client.get(self.url)
        _, q = self.answer(1, formal=False)
        self.assertFalse(UserPracticeMark.objects.get(object_id=q["formal"].id).is_known)
        resp = self.client.get(f"{self.url}?chuong=all&i=99")
        self.assertTrue(resp.context["result"])
        self.assertEqual(resp.context["score"], 0)
        self.assertEqual(len(resp.context["items"]), services.ROUND_SIZE)

    def test_changing_group_starts_new_round(self):
        self.client.get(self.url)
        self.client.get(f"{self.url}?chuong=1-4")
        state = self.client.session[views.SESSION_KEY]
        self.assertEqual(state["group"], "1-4")
        self.assertEqual(set(state["ids"]), {l.id for l in self.lessons[:6]})

    def test_empty_group(self):
        resp = self.client.get(f"{self.url}?chuong=9-12")
        self.assertTrue(resp.context["empty"])

    def test_bad_post_is_ignored(self):
        resp = self.client.post(reverse("lessons:polite_answer"), {"i": "x", "option": "1"})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(UserPracticeMark.objects.exists())


class IndexViewTests(PracticeViewTestCase):
    def test_units_and_open_unit_follow_progress(self):
        resp = self.client.get(reverse("lessons:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u["unit"].number for u in resp.context["units"]], [1, 5])
        self.assertEqual(resp.context["open_unit"], 1)
        self.assertEqual(resp.context["stats"]["polite_total"], 12)
        for lesson in self.lessons[:6]:
            services.record(self.user, PRACTICE_KIND_POLITE, services.pairs([lesson])[lesson.id][0].id, True)
        resp = self.client.get(reverse("lessons:index"))
        self.assertEqual(resp.context["open_unit"], 5)
        self.assertEqual(resp.context["stats"]["polite_known"], 6)
        self.assertContains(resp, 'href="/bai/lich-su/?chuong=5-8"')

    def test_sidebar_has_lessons_group(self):
        resp = self.client.get(reverse("lessons:index"))
        self.assertContains(resp, reverse("lessons:polite"))
        self.assertEqual(resp.context["active_nav"], "lessons")


class DrillViewTests(PracticeViewTestCase):
    """T5 — L2 Luyện thay thế."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        lesson = cls.lessons[1]
        drill = Drill.objects.create(lesson=lesson, example_prompt_jp="山川物産、佐藤課長",
                                     example_answer_jp="こちら、山川物産の佐藤課長です。")
        cls.items = [DrillItem.objects.create(drill=drill, number=n, prompt_jp=f"会社{n}、<b>人{n}</b>",
                                              answer_jp=f"こちら、会社{n}の人{n}です。") for n in (1, 2, 3)]
        cls.url = reverse("lessons:drill", args=[lesson.scene_no])
        cls.mark_url = reverse("lessons:drill_mark", args=[lesson.scene_no])

    def mark(self, item, ok, nxt="", **extra):
        return self.client.post(self.mark_url, {"item": item.id, "ok": "1" if ok else "0", "next": nxt, **extra})

    def test_login_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.mark(self.items[0], True).status_code, 302)
        self.assertFalse(UserPracticeMark.objects.exists())

    def test_lesson_without_drill_is_404(self):
        self.assertEqual(self.client.get(reverse("lessons:drill", args=[1])).status_code, 404)
        self.assertEqual(self.client.get(reverse("lessons:drill", args=[99])).status_code, 404)

    def test_walk_through_and_marks_are_updated(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["current"], self.items[0])
        self.assertEqual(resp.context["next_number"], 2)
        self.assertContains(resp, "会社1、&lt;b&gt;人1&lt;/b&gt;")  # chữ được escape
        self.assertRedirects(self.mark(self.items[0], True, nxt="2"), f"{self.url}?n=2")
        self.assertRedirects(self.mark(self.items[1], False, nxt="3"), f"{self.url}?n=3", fetch_redirect_response=False)
        self.assertRedirects(self.mark(self.items[2], True), f"{self.url}?xong=1", fetch_redirect_response=False)
        self.mark(self.items[1], True, nxt="3")  # chấm lại: ghi đè, cộng số lần
        mark = UserPracticeMark.objects.get(user=self.user, kind=PRACTICE_KIND_DRILL, object_id=self.items[1].id)
        self.assertEqual((mark.is_known, mark.times), (True, 2))
        resp = self.client.get(f"{self.url}?xong=1")
        self.assertTrue(resp.context["done"])
        self.assertEqual(resp.context["said"], 3)
        self.assertFalse(resp.context["any_left"])

    def test_retry_only_asks_not_yet_said(self):
        self.mark(self.items[0], True)
        self.mark(self.items[1], False)
        resp = self.client.get(f"{self.url}?lai=1")
        self.assertEqual(resp.context["current"], self.items[1])
        self.assertEqual(resp.context["next_number"], 3)
        self.assertRedirects(self.mark(self.items[2], True, lai="1"), f"{self.url}?lai=1&xong=1",
                             fetch_redirect_response=False)

    def test_item_of_other_lesson_is_rejected(self):
        other = reverse("lessons:drill_mark", args=[self.lessons[0].scene_no])
        self.client.post(other, {"item": self.items[0].id, "ok": "1"})
        self.assertFalse(UserPracticeMark.objects.exists())

    def test_overview_links_drill(self):
        resp = self.client.get(reverse("lessons:index"))
        self.assertEqual(resp.context["next_drill"], self.lessons[1])
        self.assertContains(resp, f'href="{self.url}"')


class RoleplayViewTests(PracticeViewTestCase):
    """T6 — L3 Hội thoại đóng vai."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rp = Roleplay.objects.get(unit=cls.u1, number=1)
        RoleplayLine.objects.create(roleplay=cls.rp, number=1, speaker="Ms.Nakagawa", text_jp="はじめまして。<i>中川</i>です。")
        RoleplayLine.objects.create(roleplay=cls.rp, number=2, speaker="Mr.Smith", text_jp="{1}。スミスです。{2}。")
        RoleplayLine.objects.create(roleplay=cls.rp, number=3, speaker="Mr.Smith", text_jp="{3}")
        cls.blanks = [RoleplayBlank.objects.create(roleplay=cls.rp, number=n, answer_jp=a)
                      for n, a in ((1, "はじめまして"), (2, "よろしくお願いします"), (3, "これをどうぞ"))]
        cls.url = reverse("lessons:roleplay", args=[1, 1])
        cls.mark_url = reverse("lessons:roleplay_mark", args=[1, 1])

    def test_line_parts(self):
        blanks = {b.number: b for b in self.blanks}
        parts = services.line_parts("{1}。スミスです。{2}。{9}", blanks)
        self.assertEqual(parts, [{"blank": self.blanks[0]}, {"text": "。スミスです。"}, {"blank": self.blanks[1]},
                                 {"text": "。{9}"}])

    def test_three_blanks_and_escaped_text(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'class="ls-blank"', count=3)
        self.assertContains(resp, "&lt;i&gt;中川&lt;/i&gt;")
        self.assertNotContains(resp, "<i>中川</i>")
        self.assertEqual(resp.context["me"], "Mr.Smith")
        self.assertNotContains(resp, "<details class=\"ls-blank\" id=\"o1\" open")

    def test_mark_keeps_blank_open_and_records(self):
        resp = self.client.post(self.mark_url, {"blank": self.blanks[0].id, "ok": "1", "mo": "3"})
        self.assertRedirects(resp, f"{self.url}?mo=1,3#o1", fetch_redirect_response=False)
        mark = UserPracticeMark.objects.get(user=self.user, kind=PRACTICE_KIND_BLANK, object_id=self.blanks[0].id)
        self.assertTrue(mark.is_known)
        resp = self.client.get(f"{self.url}?mo=1,3")
        self.assertContains(resp, '<details class="ls-blank" id="o1" open>')
        self.assertContains(resp, '<details class="ls-blank" id="o3" open>')
        self.assertContains(resp, '<details class="ls-blank" id="o2">')
        self.assertEqual(resp.context["said"], 1)

    def test_show_all_opens_every_blank(self):
        resp = self.client.get(f"{self.url}?all=1")
        for n in (1, 2, 3):
            self.assertContains(resp, f'id="o{n}" open>')

    def test_blank_of_other_roleplay_rejected_and_missing_is_404(self):
        self.client.post(reverse("lessons:roleplay_mark", args=[5, 1]), {"blank": self.blanks[0].id, "ok": "1"})
        self.assertFalse(UserPracticeMark.objects.exists())
        self.assertEqual(self.client.get(reverse("lessons:roleplay", args=[1, 2])).status_code, 404)

    def test_overview_marks_roleplay_done(self):
        for b in self.blanks:
            services.record(self.user, PRACTICE_KIND_BLANK, b.id, True)
        resp = self.client.get(reverse("lessons:index"))
        self.assertContains(resp, f'class="tag is-ok" href="{self.url}"')
        self.assertEqual(resp.context["stats"]["blank_known"], 3)


class ProgressTests(PracticeViewTestCase):
    """T8 — Học tiếp, Câu chưa thuộc (chuỗi luyện lại qua nhiều bài), tiến độ chương."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.items = {}
        for lesson in (cls.lessons[1], cls.lessons[3], cls.lessons[8]):
            drill = Drill.objects.create(lesson=lesson, example_prompt_jp="a", example_answer_jp="b")
            cls.items[lesson.scene_no] = [DrillItem.objects.create(drill=drill, number=n, prompt_jp=f"p{n}",
                                                                   answer_jp=f"a{n}") for n in (1, 2, 3)]
        cls.rp = Roleplay.objects.get(unit=cls.u1, number=1)
        RoleplayLine.objects.create(roleplay=cls.rp, number=1, speaker="A", text_jp="{1}{2}")
        cls.blanks = [RoleplayBlank.objects.create(roleplay=cls.rp, number=n, answer_jp="x") for n in (1, 2)]

    def overview(self):
        return self.client.get(reverse("lessons:index")).context

    def test_fresh_user_resumes_first_drill_and_has_no_retry(self):
        ctx = self.overview()
        self.assertEqual(ctx["resume"]["lesson"], self.lessons[1])
        self.assertIsNone(ctx["resume"]["at"])
        self.assertEqual((ctx["retry"]["drill"], ctx["retry"]["blank"], ctx["retry"]["polite"]), (0, 0, 0))
        u1 = ctx["units"][0]
        self.assertEqual((u1["known"], u1["total"]), (0, 6 + 6 + 2))  # 2 drill × 3 + 6 cặp + 2 ô

    def test_resume_follows_last_practiced_until_finished(self):
        services.record(self.user, PRACTICE_KIND_DRILL, self.items[9][0].id, True)
        ctx = self.overview()
        self.assertEqual(ctx["resume"]["lesson"].scene_no, 9)
        self.assertEqual((ctx["resume"]["known"], ctx["resume"]["total"]), (1, 3))
        services.record(self.user, PRACTICE_KIND_BLANK, self.blanks[0].id, False)
        self.assertEqual(self.overview()["resume"]["roleplay"], self.rp)
        for b in self.blanks:
            services.record(self.user, PRACTICE_KIND_BLANK, b.id, True)
        self.assertEqual(self.overview()["resume"]["lesson"], self.lessons[1])  # đoạn xong -> drill chưa xong đầu

    def test_retry_counts_and_unit_progress(self):
        services.record(self.user, PRACTICE_KIND_DRILL, self.items[4][1].id, False)
        services.record(self.user, PRACTICE_KIND_DRILL, self.items[9][0].id, False)
        services.record(self.user, PRACTICE_KIND_DRILL, self.items[2][0].id, True)
        services.record(self.user, PRACTICE_KIND_BLANK, self.blanks[1].id, False)
        formal = services.pairs([self.lessons[0]])[self.lessons[0].id][0]
        services.record(self.user, PRACTICE_KIND_POLITE, formal.id, False)
        resp = self.client.get(reverse("lessons:index"))
        retry = resp.context["retry"]
        self.assertEqual((retry["drill"], retry["blank"], retry["polite"]), (2, 1, 1))
        self.assertEqual(retry["drill_lesson"], self.lessons[3])
        self.assertEqual(retry["roleplay"], self.rp)
        self.assertContains(resp, f'href="{reverse("lessons:drill", args=[4])}?lai=1"')
        self.assertEqual(resp.context["units"][0]["known"], 1)

    def test_retry_chain_moves_to_next_lesson_with_wrong_items(self):
        services.record(self.user, PRACTICE_KIND_DRILL, self.items[4][1].id, False)
        services.record(self.user, PRACTICE_KIND_DRILL, self.items[9][2].id, False)
        resp = self.client.get(f"{reverse('lessons:drill', args=[4])}?lai=1&xong=1")
        self.assertEqual(resp.context["next_lesson"].scene_no, 9)
        self.assertContains(resp, f'href="{reverse("lessons:drill", args=[9])}?lai=1"')
        resp = self.client.get(f"{reverse('lessons:drill', args=[9])}?lai=1&xong=1")
        self.assertIsNone(resp.context["next_lesson"])
        resp = self.client.get(f"{reverse('lessons:drill', args=[2])}?xong=1")  # không phải luyện lại: bài kế
        self.assertEqual(resp.context["next_lesson"].scene_no, 4)
