from django.urls import path

from . import views

app_name = "practice_sheets"

urlpatterns = [
    path("create/", views.create_view, name="create"),
    path("<int:pk>/download/", views.download_view, name="download"),
]
