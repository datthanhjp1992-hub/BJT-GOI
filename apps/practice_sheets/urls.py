from django.urls import path

from . import views

app_name = "practice_sheets"

urlpatterns = [
    path("create/", views.create_view, name="create"),
    # Đặt trước route <int:pk> để "mau.csv" không bị nuốt mất — cùng lý do như
    # khu nhập dữ liệu SC07b.
    path("mau.<str:fmt>", views.template_view, name="template"),
    path("<int:pk>/download/", views.download_view, name="download"),
]
