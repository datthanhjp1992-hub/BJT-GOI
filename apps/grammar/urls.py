from django.urls import path

from . import views

app_name = "grammar"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("chuong/<str:category>/", views.chapter_view, name="chapter"),
    path("chuong/<str:category>/kiem-tra/", views.quiz_view, name="quiz"),
    path("chuong/<str:category>/kiem-tra/tra-loi/", views.quiz_answer_view, name="quiz_answer"),
]
