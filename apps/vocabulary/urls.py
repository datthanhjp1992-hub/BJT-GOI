from django.urls import path

from . import views

app_name = "vocabulary"

urlpatterns = [
    # Thư viện toàn bộ từ vựng (mục "Từ vựng" trên topbar trỏ vào đây).
    path("", views.vocabulary_list_view, name="index"),
    # Cùng một view, lọc sẵn theo chủ đề.
    path("topic/<slug:topic_slug>/", views.vocabulary_list_view, name="list"),
]
