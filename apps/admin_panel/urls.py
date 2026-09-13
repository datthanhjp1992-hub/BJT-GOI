from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.overview_view, name="overview"),
    path("data/", views.data_index_view, name="data_index"),
    # Đặt trước route nhập để "mau.csv" / "xuat.xlsx" không bị nuốt mất.
    path("data/<str:model_label>/mau.<str:fmt>", views.data_template_view, name="data_template"),
    path("data/<str:model_label>/xuat.<str:fmt>", views.data_export_view, name="data_export"),
    path("data/<str:model_label>/xac-nhan/", views.data_import_confirm_view, name="data_import_confirm"),
    path("data/<str:model_label>/", views.data_import_view, name="data_import"),
]
