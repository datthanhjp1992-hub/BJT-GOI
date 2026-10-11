"""
Sinh câu hỏi cho bài Kiểm tra từ vựng — docs/SPEC_KIEM_TRA.md T7.5.

Bốn dạng (MasterCode 23): meaning (日→Việt), word (Việt→日), reading (cách đọc),
cloze (điền vào câu ví dụ). Cả lượt được sinh MỘT lần lúc bắt đầu, ghi vào
ExamAnswer.payload — xem apps/exam/models.py.

Đáp án nhiễu, theo thứ tự ưu tiên (spec T7.5):
  1. dạng reading: biến thể của chính cách đọc đúng (けっさい → けつさい, けさい,
     げっさい...) — đúng kiểu bẫy của BJT;
  2. từ cùng chủ đề (trừ topic hàng kana — chúng xếp theo chữ cái, không theo nghĩa);
  3. từ gần giống mặt chữ / cách đọc (trigram, cùng chỉ mục với ô tìm kiếm SC05);
  4. ngẫu nhiên toàn kho.
Không bao giờ có hai phương án hiển thị giống nhau, và đáp án nhiễu không được
"cũng đúng" (từ khác nhưng cùng nghĩa với đáp án ở dạng meaning, v.v.).
"""
import random
import re
import unicodedata

from django.contrib.postgres.search import TrigramSimilarity

from apps.core.constants import VOCAB_Q_CLOZE, VOCAB_Q_MEANING, VOCAB_Q_READING, VOCAB_Q_WORD
from apps.vocabulary.models import ExampleSentence, Vocabulary

from ..constants import KANA_LINE_SLUG_SUFFIX, OPTION_COUNT

CLOZE_BLANK = "（　）"
SIMILAR_MIN = 0.2
SIMILAR_LIMIT = 15
SAME_TOPIC_LIMIT = 40
RANDOM_LIMIT = 30

# =============================================================================
# Hàm thuần — không chạm DB (test bằng SimpleTestCase)
# =============================================================================

COMPOUND_RE = re.compile(r"[・=、]")
KANA_RE = re.compile(r"^[぀-ヿー・ー〜～\s]+$")

# Thêm/bớt dấu ゛ ゜ (かが, はばぱ...).
DAKUTEN = dict(zip("かきくけこさしすせそたちつてとはひふへほ", "がぎぐげござじずぜぞだぢづでどばびぶべぼ"))
HANDAKUTEN = dict(zip("はひふへほ", "ぱぴぷぺぽ"))
UNDAKU = {v: k for k, v in {**DAKUTEN, **HANDAKUTEN}.items()}
SMALL_TO_BIG = dict(zip("ゃゅょ", "やゆよ"))
# Âm có thể đứng sau っ (k, s, t, p) — chèn っ vào trước chúng ra cách đọc "gần đúng".
GEMINATE_BEFORE = set("かきくけこさしすせそたちつてとぱぴぷぺぽ")
# Hàng お và う: thêm/bớt う kéo dài (こう ↔ こ, ゆう ↔ ゆ).
O_U_ROW = set("おこごそぞとどのほぼぽもよろょうくぐすずつづぬふぶぷむゆるゅ")


def is_kana_only(text):
    """Chữ toàn kana (không có kanji) — hỏi cách đọc thì vô nghĩa."""
    return bool(KANA_RE.match(unicodedata.normalize("NFKC", text or "")))


def reading_variants(reading):
    """Các cách đọc "gần đúng" của `reading` để làm đáp án nhiễu, theo thứ tự ổn định.

    Không bao gồm chính `reading`. Chỉ biến đổi MỘT chỗ mỗi lần để biến thể
    trông thật — người học nhầm đúng kiểu đó (っ/つ, có/không trường âm, ゛).
    """
    r = reading or ""
    out = []
    for i, c in enumerate(r):
        before, after = r[:i], r[i + 1:]
        if c == "っ":
            out.append(before + "つ" + after)       # けっさい -> けつさい
            out.append(before + after)              # けっさい -> けさい
        if c in SMALL_TO_BIG:
            out.append(before + SMALL_TO_BIG[c] + after)
        if c in DAKUTEN:
            out.append(before + DAKUTEN[c] + after)  # さ -> ざ
        if c in HANDAKUTEN and i > 0:
            out.append(before + HANDAKUTEN[c] + after)
        if c in UNDAKU:
            out.append(before + UNDAKU[c] + after)   # ざ -> さ
        if c == "う" and i > 0 and r[i - 1] in O_U_ROW:
            out.append(before + after)              # こう -> こ
        if c in O_U_ROW and c != "う" and (i + 1 >= len(r) or r[i + 1] != "う"):
            out.append(before + c + "う" + after)    # こ -> こう
        if i + 1 < len(r) and r[i + 1] in GEMINATE_BEFORE and c not in "っんー" and c != r[i + 1]:
            out.append(before + c + "っ" + after)    # けさい -> けっさい
    seen, result = {r}, []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            result.append(v)
    return result


def make_cloze(sentence, word):
    """Che `word` trong câu ví dụ. Trả về None nếu câu không chứa đúng mặt chữ."""
    if not sentence or not word or word not in sentence:
        return None
    return sentence.replace(word, CLOZE_BLANK, 1)


def _key(text):
    return "".join(unicodedata.normalize("NFKC", text or "").split()).casefold()


def pick_options(correct, candidates, rng, count=OPTION_COUNT):
    """Ghép đáp án đúng với tối đa count-1 phương án nhiễu (không trùng hiển thị).

    candidates: list các dict {"text", "gloss"} THEO THỨ TỰ ƯU TIÊN, mỗi nhóm
    ưu tiên đã được xáo sẵn. Trả về (options, vị trí đúng tính từ 1).
    """
    seen = {_key(correct["text"])}
    picked = []
    for cand in candidates:
        k = _key(cand["text"])
        if not k or k in seen:
            continue
        seen.add(k)
        picked.append(cand)
        if len(picked) >= count - 1:
            break
    options = [correct] + picked
    rng.shuffle(options)
    return options, options.index(correct) + 1


# =============================================================================
# Truy vấn nguồn đáp án nhiễu
# =============================================================================

def _gloss(v):
    return f"{v.word}（{v.reading}）: {v.meaning_vi}"


def _same_topic(vocab, rng):
    topic_ids = [t.pk for t in vocab.topics.all() if not t.slug.endswith(KANA_LINE_SLUG_SUFFIX)]
    if not topic_ids:
        return []
    rows = list(
        Vocabulary.objects.filter(topics__in=topic_ids).exclude(pk=vocab.pk).distinct()
        .order_by("?")[:SAME_TOPIC_LIMIT]
    )
    rng.shuffle(rows)
    return rows


def _similar(vocab, field):
    value = getattr(vocab, field)
    return list(
        Vocabulary.objects.annotate(sim=TrigramSimilarity(field, value))
        .filter(sim__gte=SIMILAR_MIN).exclude(pk=vocab.pk)
        .order_by("-sim")[:SIMILAR_LIMIT]
    )


def _random(vocab):
    return list(Vocabulary.objects.exclude(pk=vocab.pk).order_by("?")[:RANDOM_LIMIT])


def _distractor_words(vocab, rng, similar_field):
    """Từ làm nguồn nhiễu, ưu tiên cùng chủ đề -> gần giống -> ngẫu nhiên."""
    seen, words = {vocab.pk}, []
    for group in (_same_topic(vocab, rng), _similar(vocab, similar_field), _random(vocab)):
        for v in group:
            if v.pk not in seen:
                seen.add(v.pk)
                words.append(v)
    return words


# =============================================================================
# Sinh một câu
# =============================================================================

def _base_payload(vocab):
    return {"word": vocab.word, "reading": vocab.reading, "meaning": vocab.meaning_vi}


def build_meaning(vocab, rng):
    same_word = _key(vocab.word)
    correct_meaning = _key(vocab.meaning_vi)
    cands = [
        {"text": v.meaning_vi, "gloss": _gloss(v)}
        for v in _distractor_words(vocab, rng, "word")
        if _key(v.word) != same_word and _key(v.meaning_vi) != correct_meaning
    ]
    options, correct = pick_options({"text": vocab.meaning_vi, "gloss": ""}, cands, rng)
    return {**_base_payload(vocab), "prompt": vocab.word, "options": options, "correct": correct}


def build_word(vocab, rng, prompt=None):
    correct_meaning = _key(vocab.meaning_vi)
    cands = [
        {"text": v.word, "gloss": _gloss(v)}
        for v in _distractor_words(vocab, rng, "word")
        # Từ khác mà cùng nghĩa thì cũng "đúng" -> không được làm nhiễu.
        if _key(v.meaning_vi) != correct_meaning
    ]
    options, correct = pick_options({"text": vocab.word, "gloss": ""}, cands, rng)
    return {**_base_payload(vocab), "prompt": prompt or vocab.meaning_vi, "options": options, "correct": correct}


def build_reading(vocab, rng):
    variants = reading_variants(vocab.reading)
    rng.shuffle(variants)
    cands = [{"text": v, "gloss": ""} for v in variants]
    # Thiếu biến thể (cách đọc quá ngắn) thì lấy cách đọc của từ cùng chữ đầu / gần giống.
    first = vocab.word[:1]
    near = list(Vocabulary.objects.filter(word__startswith=first).exclude(pk=vocab.pk)[:SIMILAR_LIMIT])
    rng.shuffle(near)
    cands += [{"text": v.reading, "gloss": _gloss(v)} for v in near + _similar(vocab, "reading")]
    options, correct = pick_options({"text": vocab.reading, "gloss": ""}, cands, rng)
    return {**_base_payload(vocab), "prompt": vocab.word, "options": options, "correct": correct}


def build_cloze(vocab, rng, sentence):
    payload = build_word(vocab, rng, prompt=make_cloze(sentence.sentence_jp, vocab.word))
    payload["sentence_vi"] = sentence.sentence_vi
    return payload


def cloze_sentence(vocab):
    """Câu ví dụ chứa ĐÚNG mặt chữ của từ (để che được), None nếu không có."""
    return ExampleSentence.objects.filter(vocabulary=vocab, sentence_jp__contains=vocab.word).order_by("pk").first()


def is_compound_entry(word):
    """Ô gộp nhiều dạng (方針=方策=政策, A・B, A、B) — chỉ hỏi nghĩa / chọn từ được,
    hỏi cách đọc hay điền vào câu thì đáp án dài và gượng."""
    return bool(COMPOUND_RE.search(unicodedata.normalize("NFKC", word or "")))


def can_ask(vocab, qtype):
    if qtype in (VOCAB_Q_READING, VOCAB_Q_CLOZE) and is_compound_entry(vocab.word):
        return False
    if qtype == VOCAB_Q_READING:
        return not is_kana_only(vocab.word) and _key(vocab.word) != _key(vocab.reading)
    if qtype == VOCAB_Q_CLOZE:
        return cloze_sentence(vocab) is not None
    return True


def build_question(vocab, qtype, rng):
    if qtype == VOCAB_Q_READING:
        return build_reading(vocab, rng)
    if qtype == VOCAB_Q_WORD:
        return build_word(vocab, rng)
    if qtype == VOCAB_Q_CLOZE:
        return build_cloze(vocab, rng, cloze_sentence(vocab))
    return build_meaning(vocab, rng)


def plan_types(words, types, rng):
    """Gán mỗi từ một dạng câu, chia đều các dạng đã chọn.

    Từ không hỏi được dạng được gán (reading cho từ toàn kana, cloze cho từ
    không có câu ví dụ) thì thử dạng kế tiếp trong vòng; hết cách thì về meaning.
    Trả về list (vocab, qtype).
    """
    types = [t for t in types if t] or [VOCAB_Q_MEANING]
    rotation = list(types)
    rng.shuffle(rotation)
    plan = []
    for i, vocab in enumerate(words):
        chosen = VOCAB_Q_MEANING
        for k in range(len(rotation)):
            qtype = rotation[(i + k) % len(rotation)]
            if can_ask(vocab, qtype):
                chosen = qtype
                break
        plan.append((vocab, chosen))
    return plan


def build(words, types, rng=None):
    """Sinh trọn lượt: list (vocab, qtype, payload) theo thứ tự hiện."""
    rng = rng or random.Random()
    words = list(words)
    rng.shuffle(words)
    return [(vocab, qtype, build_question(vocab, qtype, rng)) for vocab, qtype in plan_types(words, types, rng)]


def candidate_words(qs):
    """Nạp sẵn topics để _same_topic khỏi tốn thêm một query mỗi từ cho việc đọc slug."""
    return qs.prefetch_related("topics")

