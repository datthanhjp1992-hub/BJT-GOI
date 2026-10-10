from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    # Nút "Học hôm nay" của SC03 — hàng đợi gom mọi chủ đề, chạy bằng luồng study_*.
    path("daily/start/", views.daily_start_view, name="daily_start"),
    path("flashcard/<slug:topic_slug>/", views.flashcard_view, name="flashcard"),
    path("flashcard/<slug:topic_slug>/more-new/", views.flashcard_more_new_view, name="flashcard_more_new"),
    path("flashcard/<slug:topic_slug>/end/", views.flashcard_end_view, name="flashcard_end"),
    # Ô "Không hiện lại" trên bảng hướng dẫn vuốt thẻ (spec.md T6.6).
    path("swipe-coach/off/", views.swipe_coach_off_view, name="swipe_coach_off"),
    path("flashcard/review/<int:vocabulary_id>/", views.flashcard_review, name="flashcard_review"),
    path("flashcard/comment/<int:vocabulary_id>/", views.flashcard_comment, name="flashcard_comment"),
    # Hoàn tác lần chấm gần nhất (SC04 và phiên theo hàng đợi dùng chung).
    path("undo/", views.undo_view, name="undo"),
    # Phiên học theo BỘ LỌC của SC05 (nhiều chủ đề trong một hàng đợi).
    path("study/start/", views.study_start_view, name="study_start"),
    path("study/", views.study_view, name="study"),
    path("study/review/<int:vocabulary_id>/", views.study_review_view, name="study_review"),
    path("study/end/", views.study_end_view, name="study_end"),
    path("study/retry/", views.study_retry_view, name="study_retry"),
    # spec.md T4.3 — học liền mạch: lô lệnh chấm gửi ngầm, tải thêm thẻ, bình luận.
    path("study/sync/", views.study_sync_view, name="study_sync"),
    path("study/cards/", views.study_cards_view, name="study_cards"),
    path("study/card/<int:vocabulary_id>/discussion/", views.study_discussion_view, name="study_discussion"),
    # SC15 Ôn tập — thống kê từ đã học + các lối vào một lượt ôn.
    path("review/", views.review_view, name="review"),
    path("review/start/", views.review_start_view, name="review_start"),
    # Trắc nghiệm trên hàng đợi đã chốt (không gắn với một chủ đề nào).
    path("study/quiz/", views.study_quiz_view, name="study_quiz"),
    path("study/quiz/<int:vocabulary_id>/", views.study_quiz_answer_view, name="study_quiz_answer"),
    path("quiz/<slug:topic_slug>/", views.quiz_view, name="quiz"),
    path("quiz/<slug:topic_slug>/answer/<int:vocabulary_id>/", views.quiz_answer_view, name="quiz_answer"),
]
