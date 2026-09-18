from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("flashcard/<slug:topic_slug>/", views.flashcard_view, name="flashcard"),
    path("flashcard/review/<int:vocabulary_id>/", views.flashcard_review, name="flashcard_review"),
    path("flashcard/comment/<int:vocabulary_id>/", views.flashcard_comment, name="flashcard_comment"),
    # Phiên học theo BỘ LỌC của SC05 (nhiều chủ đề trong một hàng đợi).
    path("study/start/", views.study_start_view, name="study_start"),
    path("study/", views.study_view, name="study"),
    path("study/review/<int:vocabulary_id>/", views.study_review_view, name="study_review"),
    path("study/end/", views.study_end_view, name="study_end"),
    path("quiz/<slug:topic_slug>/", views.quiz_view, name="quiz"),
    path("quiz/<slug:topic_slug>/answer/<int:vocabulary_id>/", views.quiz_answer_view, name="quiz_answer"),
]
