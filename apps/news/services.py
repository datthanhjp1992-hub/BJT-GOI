"""Gạch chân từ có trong kho từ vựng — docs/SPEC_NGHE_BAN_TIN.md mục 6.

shortcut: so chuỗi con, không chia động từ (乗り切った không khớp 乗り切る); nếu cần thì thêm bộ tách từ sau.
"""
import re

from apps.vocabulary.models import Vocabulary

_KANA_ONLY = re.compile(r"[぀-ヿー]+")


def vocab_terms():
    """[(chuỗi cần tìm, Vocabulary)] — dài trước. Từ kana ngắn (うち, こと…) dễ khớp nhầm nên bỏ."""
    terms = []
    for v in Vocabulary.objects.only("id", "word", "reading", "meaning_vi"):
        term = v.word[:-2] if v.word.endswith("する") else v.word
        if len(term) < 2 or (_KANA_ONLY.fullmatch(term) and len(term) < 4):
            continue
        terms.append((term, v))
    terms.sort(key=lambda t: len(t[0]), reverse=True)
    return terms


def highlight(text, terms):
    """Cắt `text` thành [(đoạn, đối tượng | None)]: quét trái→phải, term dài trước, không chồng lấn."""
    by_first = {}  # tra theo ký tự đầu thay vì thử cả ~3.500 term ở mỗi vị trí
    for term, obj in terms:
        by_first.setdefault(term[0], []).append((term, obj))
    parts, plain, i = [], "", 0
    while i < len(text):
        for term, obj in by_first.get(text[i], ()):
            if text.startswith(term, i):
                if plain:
                    parts.append((plain, None))
                    plain = ""
                parts.append((term, obj))
                i += len(term)
                break
        else:
            plain += text[i]
            i += 1
    if plain:
        parts.append((plain, None))
    return parts
