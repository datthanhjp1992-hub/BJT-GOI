from django.urls import path

from . import views

app_name = "grammar"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("chuong/<str:category>/", views.chapter_view, name="chapter"),
]
