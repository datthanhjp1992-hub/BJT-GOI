"""
Test các hàm thuần của khu Kiểm tra — không cần DB (SimpleTestCase).

Chạy: python manage.py test apps.exam.tests.test_pure
"""
import random
from datetime import timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core import quiz
from apps.core.constants import EXAM_MODE_EXAM, EXAM_MODE_PRACTICE, VOCAB_Q_MEANING, VOCAB_Q_READING
from apps.exam.constants import PART_MINUTES
from apps.exam.services import timing, vocab_quiz


class ReadingVariantTests(SimpleTestCase):
    def test_sokuon_variants_are_bjt_style_traps(self):
        variants = vocab_quiz.reading_variants("けっさい")
        self.assertIn("けつさい", variants)   # っ -> つ
        self.assertIn("けさい", variants)     # bỏ っ
        self.assertIn("げっさい", variants)   # thêm ゛
        self.assertNotIn("けっさい", variants)

    def test_long_vowel_added_and_removed(self):
        self.assertIn("こしょ", vocab_quiz.reading_variants("こうしょ"))
        self.assertIn("こうしょう", vocab_quiz.reading_variants("こうしょ"))

    def test_no_duplicates(self):
        variants = vocab_quiz.reading_variants("しゅっちょう")
        self.assertEqual(len(variants), len(set(variants)))

    def test_empty_reading(self):
        self.assertEqual(vocab_quiz.reading_variants(""), [])


class HelperTests(SimpleTestCase):
    def test_kana_only(self):
        self.assertTrue(vocab_quiz.is_kana_only("アクセス"))
        self.assertTrue(vocab_quiz.is_kana_only("ざっくり"))
        self.assertFalse(vocab_quiz.is_kana_only("決裁"))
        self.assertFalse(vocab_quiz.is_kana_only("手を打つ"))

    def test_make_cloze_hides_first_occurrence_only(self):
        self.assertEqual(vocab_quiz.make_cloze("資料に目を通す。目を通す", "目を通す"), "資料に（　）。目を通す")

    def test_make_cloze_none_when_word_missing(self):
        self.assertIsNone(vocab_quiz.make_cloze("資料を読む。", "目を通す"))

    def test_pick_options_dedupes_display_text(self):
        rng = random.Random(1)
        correct = {"text": "けっさい", "gloss": ""}
        cands = [{"text": "けっさい", "gloss": ""}, {"text": "けつさい", "gloss": ""},
                 {"text": "けつさい ", "gloss": ""}, {"text": "けさい", "gloss": ""}, {"text": "げっさい", "gloss": ""}]
        options, pos = vocab_quiz.pick_options(correct, cands, rng)
        texts = [o["text"] for o in options]
        self.assertEqual(len(texts), 4)
        self.assertEqual(texts[pos - 1], "けっさい")
        self.assertEqual(len({t.strip() for t in texts}), 4)

    def test_pick_options_with_few_candidates(self):
        options, pos = vocab_quiz.pick_options({"text": "a", "gloss": ""}, [], random.Random(0))
        self.assertEqual(options, [{"text": "a", "gloss": ""}])
        self.assertEqual(pos, 1)

    def test_plan_types_skips_reading_for_kana_words(self):
        words = [SimpleNamespace(word="アクセス", reading="アクセス"), SimpleNamespace(word="決裁", reading="けっさい")]
        plan = vocab_quiz.plan_types(words, [VOCAB_Q_READING], random.Random(0))
        self.assertEqual(plan[0][1], VOCAB_Q_MEANING)
        self.assertEqual(plan[1][1], VOCAB_Q_READING)

    def test_compound_entries_only_get_meaning_questions(self):
        words = [SimpleNamespace(word="方針=方策=政策", reading="ほうしん・ほうさく・せいさく")]
        self.assertTrue(vocab_quiz.is_compound_entry("ぎりぎり、ぎりぎりの線"))
        self.assertFalse(vocab_quiz.is_compound_entry("決裁"))
        plan = vocab_quiz.plan_types(words, [VOCAB_Q_READING], random.Random(0))
        self.assertEqual(plan[0][1], VOCAB_Q_MEANING)

    def test_plan_types_spreads_types_evenly(self):
        words = [SimpleNamespace(word=f"語{i}", reading=f"ご{i}") for i in range(6)]
        plan = vocab_quiz.plan_types(words, [VOCAB_Q_MEANING, VOCAB_Q_READING], random.Random(3))
        kinds = [q for _, q in plan]
        self.assertEqual(kinds.count(VOCAB_Q_MEANING), 3)
        self.assertEqual(kinds.count(VOCAB_Q_READING), 3)


class QuizScoreTests(SimpleTestCase):
    def test_levels(self):
        self.assertEqual(quiz.score_level(8, 10), "hi")
        self.assertEqual(quiz.score_level(5, 10), "mid")
        self.assertEqual(quiz.score_level(4, 10), "lo")
        self.assertEqual(quiz.percent(1, 0), 0)


def _attempt(mode=EXAM_MODE_EXAM, started=None, submitted=None):
    started = started or {}
    return SimpleNamespace(
        mode_code=mode,
        part_started_at={str(k): v.isoformat() for k, v in started.items()},
        part_submitted_at=submitted or {},
    )


def _answer(order, part):
    return SimpleNamespace(order=order, question_id=1, question=SimpleNamespace(part=part))


class TimingTests(SimpleTestCase):
    def test_deadline_only_in_exam_mode(self):
        now = timezone.now()
        self.assertIsNone(timing.part_deadline(_attempt(EXAM_MODE_PRACTICE, {1: now}), 1))
        self.assertEqual(timing.part_deadline(_attempt(started={1: now}), 1), now + timedelta(minutes=PART_MINUTES[1]))

    def test_seconds_left_never_negative(self):
        long_ago = timezone.now() - timedelta(hours=5)
        self.assertEqual(timing.seconds_left(_attempt(started={2: long_ago}), 2), 0)
        self.assertTrue(timing.is_part_closed(_attempt(started={2: long_ago}), 2))

    def test_listening_part_locks_passed_questions(self):
        attempt = _attempt(started={1: timezone.now()})
        self.assertTrue(timing.is_locked(attempt, _answer(2, part=1), current_order=3))
        self.assertFalse(timing.is_locked(attempt, _answer(3, part=1), current_order=3))

    def test_reading_part_allows_going_back(self):
        attempt = _attempt(started={3: timezone.now()})
        self.assertFalse(timing.is_locked(attempt, _answer(70, part=3), current_order=80))

    def test_submitted_part_is_locked(self):
        attempt = _attempt(started={3: timezone.now()}, submitted={"3": timezone.now().isoformat()})
        self.assertTrue(timing.is_locked(attempt, _answer(70, part=3), current_order=80))

    def test_practice_mode_never_locks(self):
        attempt = _attempt(EXAM_MODE_PRACTICE, started={1: timezone.now()})
        self.assertFalse(timing.is_locked(attempt, _answer(1, part=1), current_order=5))


class AudioUrlTests(SimpleTestCase):
    def q(self, path="mock/q031_part1_sec1.mp3", version=1):
        return SimpleNamespace(audio_path=path, audio_version=version)

    def test_builds_versioned_url(self):
        from django.test import override_settings

        from apps.exam.audio import exam_audio_url
        with override_settings(EXAM_AUDIO_BASE_URL="https://x.supabase.co/storage/v1/object/public/exam-audio"):
            self.assertEqual(exam_audio_url(self.q(version=3)),
                             "https://x.supabase.co/storage/v1/object/public/exam-audio/mock/q031_part1_sec1.mp3?v=3")

    def test_empty_without_base_or_audio(self):
        from django.test import override_settings

        from apps.exam.audio import exam_audio_url
        with override_settings(EXAM_AUDIO_BASE_URL=""):
            self.assertEqual(exam_audio_url(self.q()), "")
        with override_settings(EXAM_AUDIO_BASE_URL="https://x/"):
            self.assertEqual(exam_audio_url(self.q(path="")), "")

    def test_upload_plan(self):
        from apps.exam.audio import UPLOAD_NEW, UPLOAD_OVERWRITE, UPLOAD_SAME, plan_uploads
        local = {"mock/a.mp3": "aaa", "mock/b.mp3": "bbb", "mock/c.mp3": "ccc"}
        remote = {"mock/a.mp3": '"AAA"', "mock/b.mp3": '"old"', "mock/z.mp3": '"zzz"'}
        plan, orphans = plan_uploads(local, remote)
        self.assertEqual(plan, [("mock/a.mp3", UPLOAD_SAME), ("mock/b.mp3", UPLOAD_OVERWRITE),
                                ("mock/c.mp3", UPLOAD_NEW)])
        self.assertEqual(orphans, ["mock/z.mp3"])
