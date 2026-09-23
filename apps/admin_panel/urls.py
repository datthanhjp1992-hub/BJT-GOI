from django.urls import path

from . import views

app_name = "admin_panel"

urlpatterns = [
    path("", views.overview_view, name="overview"),
    path("contributions/", views.contribution_inbox_view, name="contribution_inbox"),
    path("contributions/<int:pk>/xu-ly/", views.contribution_action_view, name="contribution_action"),
    path("error-reports/", views.error_report_list_view, name="error_report_list"),
    path("error-reports/<int:pk>/xu-ly/", views.error_report_action_view, name="error_report_action"),
    path("system/", views.system_settings_view, name="system_settings"),
    path("system/ping-thu/", views.system_ping_now_view, name="system_ping_now"),
    path("data/", views.data_index_view, name="data_index"),
    # Đặt trước route nhập để "mau.csv" / "xuat.xlsx" không bị nuốt mất.
    path("data/<str:model_label>/mau.<str:fmt>", views.data_template_view, name="data_template"),
    path("data/<str:model_label>/xuat.<str:fmt>", views.data_export_view, name="data_export"),
    path(
        "data/<str:model_label>/ket-qua.<str:fmt>",
        views.data_import_preview_export_view,
        name="data_import_preview_export",
    ),
    path("data/<str:model_label>/xac-nhan/", views.data_import_confirm_view, name="data_import_confirm"),
    path("data/<str:model_label>/", views.data_import_view, name="data_import"),
]
