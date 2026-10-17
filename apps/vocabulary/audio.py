"""
Hàm thuần cho audio VOICEVOX của từ vựng / câu ví dụ (scripts/generate_vocab_audio.py).
Tách ra đây để test không cần engine.
"""
import re
import unicodedata

_VOWEL_KANA = {"a": "あ", "i": "い", "u": "う", "e": "え", "o": "お"}


def speak_text(text):
    """Bỏ mọi khoảng trắng: engine tách sai 「50 人」→ ごじゅう、ひと, 「1000 語」→ せん、かたり."""
    return "".join(str(text or "").split())


def base_form(text):
    """Bỏ ghi chú trên DB trước khi đọc: phần trong ngoặc （売出し）/（する）, dấu ～,
    cách đọc thứ hai sau / (みょうごにち/あさって → みょうごにち)."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = re.sub(r"\([^)]*\)", "", text).replace("~", "").replace("〜", "")
    return speak_text(re.split(r"/", text)[0])


def word_candidates(word):
    """Các cách đưa chữ cho engine, thử lần lượt: 'デフレ略' / '拝見敬' là ghi chú 略語 / 敬語
    dính vào chữ, nhưng 戦略 / 尊敬 là từ thật — nên thử nguyên chữ trước."""
    text = base_form(word)
    out = [text]
    if len(text) > 2 and text[-1] in "略敬":
        out.append(text[:-1])
    return out


def to_hiragana(text):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def _vowel(ch):
    return unicodedata.name(ch, " ")[-1].lower()  # HIRAGANA LETTER KO -> o


def phonetic(text):
    """Về dạng phát âm mà audio_query ghi: こう→こお, せい→せえ, ー→nguyên âm trước, を→お.
    Chỉ giữ hiragana, để so cách đọc của engine với Vocabulary.reading."""
    out = []
    text = to_hiragana(str(text or "")).replace("を", "お").replace("づ", "ず").replace("ぢ", "じ")
    for ch in text:
        if ch == "ー" and out:
            ch = _VOWEL_KANA.get(_vowel(out[-1]), ch)
        elif out and ch == "う" and _vowel(out[-1]) == "o":
            ch = "お"
        elif out and ch == "い" and _vowel(out[-1]) == "e":
            ch = "え"
        if "ぁ" <= ch <= "ゖ":
            out.append(ch)
    return "".join(out)


def query_kana(query):
    """Cách engine hiểu câu (từ JSON của /audio_query), dạng hiragana có 、 ở chỗ ngắt."""
    parts = []
    for ph in query["accent_phrases"]:
        parts.append("".join(m["text"] for m in ph["moras"]))
        if ph.get("pause_mora"):
            parts.append("、")
    return to_hiragana("".join(parts))


def is_dirty(sentence_jp):
    """Câu ví dụ lẫn tiếng Việt hoặc số thừa sau dấu kết câu (vd 「…ならない。 117」)."""
    return bool(re.search(r"[À-ỹ]|[。！？]\s*\d+\s*$", sentence_jp or ""))


# =============================================================================
# Upload (scripts/upload_vocab_audio.py)
# =============================================================================
BUCKET = "vocab-audio"
_FILE_NAME = re.compile(r"^([we])(\d+)\.mp3$")


def parse_audio_name(name):
    """'w12.mp3' -> ('w', 12) (Vocabulary), 'e7.mp3' -> ('e', 7) (ExampleSentence), khác -> None."""
    m = _FILE_NAME.match(name)
    return (m.group(1), int(m.group(2))) if m else None


def public_audio_url(base_url, name, md5):
    """URL public trên bucket; ?v= là md5 rút gọn nên file đổi nội dung thì URL đổi,
    CDN và trình duyệt lấy bản mới ngay (cache-control để 1 năm)."""
    return f"{base_url.rstrip('/')}/storage/v1/object/public/{BUCKET}/{name}?v={md5[:8]}"
