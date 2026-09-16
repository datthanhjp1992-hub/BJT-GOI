from django.urls import path

from . import views

app_name = "error_reports"

urlpatterns = [
    path("", views.my_reports_view, name="mine"),
    path("new/", views.report_create_view, name="create"),
]
