"""
Hàm chấm điểm dùng chung cho mọi bài làm có điểm: bài tập kính ngữ
(apps.keigo, SC20-SC22) và khu Kiểm tra (apps.exam, docs/SPEC_KIEM_TRA.md).

Tách ra từ apps/keigo/exercises.py (11/10/2026, spec T7.4) để hai app cùng một
ngưỡng màu điểm — keigo vẫn gọi qua exercises.percent / exercises.score_level.
"""

# Ngưỡng màu điểm: >= 80% "hi", >= 50% "mid", còn lại "lo" (class .s-hi/.s-mid/.s-lo).
LEVEL_HI = 80
LEVEL_MID = 50


def percent(score, total):
    return round(score * 100 / total) if total else 0


def score_level(score, total):
    p = percent(score, total)
    if p >= LEVEL_HI:
        return "hi"
    if p >= LEVEL_MID:
        return "mid"
    return "lo"
