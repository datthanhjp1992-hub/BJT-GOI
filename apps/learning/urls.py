from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("flashcard/<slug:topic_slug>/", views.flashcard_view, name="flashcard"),
    path("flashcard/review/<int:vocabulary_id>/", views.flashcard_review, name="flashcard_review"),
    path("quiz/<slug:topic_slug>/", views.quiz_view, name="quiz"),
]
