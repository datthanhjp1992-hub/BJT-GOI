from django.urls import path

from . import views

app_name = "news"

urlpatterns = [
    path("", views.index_view, name="index"),
    path("<int:number>/", views.lesson_view, name="lesson"),
    path("<int:number>/danh-dau/", views.mark_view, name="mark"),
]
