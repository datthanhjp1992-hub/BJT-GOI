"""
Lập lịch ôn tập kiểu Anki: SM-2 có thêm các BƯỚC HỌC tính bằng phút.

Hàm thuần — không chạm DB, không đọc đồng hồ — để test độc lập. Phần đọc/ghi
`UserVocabularyProgress` nằm ở `apps.learning.services.review_word()`.

Vòng đời một từ:

    NEW --(chấm lần đầu)--> LEARNING --(qua hết LEARN_STEPS)--> REVIEW
                                                                 |  ^
                                                          Quên   v  | tốt nghiệp
                                                             RELEARNING

* LEARNING / RELEARNING: từ quay lại sau vài phút, NGAY TRONG PHIÊN HỌC, cho
  tới khi nhớ được qua hết các bước mới được xếp lịch theo ngày.
* REVIEW: khoảng cách tính theo ngày bằng SM-2 (ease, interval_days).
  Ba nút Khó < Nhớ < Dễ LUÔN cho ba khoảng cách khác nhau.

Thang điểm giữ nguyên SM-2 (khớp `services.QUALITY_MAP`):
    0 = Quên rồi   3 = Khó   4 = Nhớ   5 = Dễ
"""
from dataclasses import dataclass, replace
from datetime import timedelta

NEW = "new"
LEARNING = "learning"
REVIEW = "review"
RELEARNING = "relearning"
CARD_STATES = (NEW, LEARNING, REVIEW, RELEARNING)
IN_SESSION_STATES = (NEW, LEARNING, RELEARNING)

AGAIN, HARD, GOOD, EASY = 0, 3, 4, 5
GRADES = (AGAIN, HARD, GOOD, EASY)

LEARN_STEPS = (1, 10)     # phút: từ mới -> 1 phút -> 10 phút -> tốt nghiệp
RELEARN_STEPS = (10,)     # phút: từ đang ôn mà quên -> 10 phút -> quay lại REVIEW
GRADUATE_INTERVAL = 1     # ngày, bấm "Nhớ" ở bước học cuối
EASY_INTERVAL = 4         # ngày, bấm "Dễ" khi đang học
SECOND_INTERVAL = 6       # ngày, lần ôn thành công thứ hai (SM-2 gốc)
HARD_FACTOR = 1.2
EASY_BONUS = 1.3
LAPSE_EASE_PENALTY = 0.2

MIN_EASE = 1.3
DEFAULT_EASE = 2.5


@dataclass
class Card:
    state: str = NEW
    step: int = 0
    ease: float = DEFAULT_EASE
    interval_days: int = 0
    repetitions: int = 0   # = UserVocabularyProgress.srs_level


@dataclass
class Result:
    card: Card
    delay: timedelta  # bao lâu nữa từ này đến hạn lại

    @property
    def in_session(self):
        """True nếu từ sẽ quay lại ngay trong phiên (tính bằng phút)."""
        return self.card.state in (LEARNING, RELEARNING)


def _hard_delay(steps, step):
    """"Khó" khi đang học = lặp lại bước hiện tại, chậm hơn một chút."""
    nxt = steps[step + 1] if step + 1 < len(steps) else steps[step] * 2
    return (steps[step] + nxt) / 2


def _sm2_ease(ease, quality):
    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    return max(MIN_EASE, round(ease, 2))


def schedule(card, quality, overnight=False):
    """Trạng thái mới của từ sau một lần chấm + độ trễ tới lần đến hạn kế tiếp.

    `overnight=True`: từ đang học / học lại bị bỏ dở từ HÔM TRƯỚC (spec.md
    T6.2). Đã qua ít nhất một đêm thì bước 10 phút không còn ý nghĩa — "Nhớ"
    tốt nghiệp luôn. Cờ do `services` tính (hàm này không đọc đồng hồ); từ
    NEW và từ REVIEW bỏ qua cờ.
    """
    if quality not in GRADES:
        raise ValueError(f"quality phải là một trong {GRADES}")

    state = card.state if card.state in CARD_STATES else REVIEW

    # ---- Từ mới / đang học / đang học lại: đi theo các bước tính bằng phút ----
    if state in IN_SESSION_STATES:
        learn_state = RELEARNING if state == RELEARNING else LEARNING
        steps = RELEARN_STEPS if learn_state == RELEARNING else LEARN_STEPS
        step = 0 if state == NEW else min(max(card.step, 0), len(steps) - 1)
        overnight = overnight and state != NEW

        if quality == AGAIN:
            return Result(replace(card, state=learn_state, step=0),
                          timedelta(minutes=steps[0]))
        if quality == HARD:
            return Result(replace(card, state=learn_state, step=step),
                          timedelta(minutes=_hard_delay(steps, step)))
        if quality == GOOD and step + 1 < len(steps) and not overnight:
            return Result(replace(card, state=learn_state, step=step + 1),
                          timedelta(minutes=steps[step + 1]))

        # Tốt nghiệp -> REVIEW
        if learn_state == RELEARNING:
            interval = max(1, card.interval_days) + (1 if quality == EASY else 0)
        else:
            interval = EASY_INTERVAL if quality == EASY else GRADUATE_INTERVAL
        new = replace(card, state=REVIEW, step=0, interval_days=interval,
                      repetitions=max(1, card.repetitions))
        return Result(new, timedelta(days=interval))

    # ---- Từ đang ôn (REVIEW): tính theo ngày ----
    if quality == AGAIN:
        new = replace(
            card, state=RELEARNING, step=0,
            ease=max(MIN_EASE, round(card.ease - LAPSE_EASE_PENALTY, 2)),
            interval_days=1, repetitions=0,
        )
        return Result(new, timedelta(minutes=RELEARN_STEPS[0]))

    prev = max(1, card.interval_days)
    reps = card.repetitions + 1
    hard = max(prev + 1, round(prev * HARD_FACTOR))
    good = SECOND_INTERVAL if reps == 2 and prev < SECOND_INTERVAL else round(prev * card.ease)
    good = max(hard + 1, good)
    easy = max(good + 1, round(good * EASY_BONUS))
    interval = {HARD: hard, GOOD: good, EASY: easy}[quality]

    new = replace(card, state=REVIEW, step=0, ease=_sm2_ease(card.ease, quality),
                  interval_days=interval, repetitions=reps)
    return Result(new, timedelta(days=interval))


def delay_parts(delay):
    """(đơn vị, số) để template/properties tự ghép chữ — không nhét tiếng Việt vào đây.

    Đơn vị: "minutes" | "hours" | "days" | "months".
    """
    minutes = delay.total_seconds() / 60
    if minutes < 60:
        return "minutes", max(1, round(minutes))
    if minutes < 60 * 24:
        return "hours", round(minutes / 60)
    days = delay.days
    if days < 30:
        return "days", days
    return "months", round(days / 30, 1)
