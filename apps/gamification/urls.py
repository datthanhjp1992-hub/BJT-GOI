from django.urls import path

from . import views

app_name = "gamification"

urlpatterns = [
    path("", views.contribution_view, name="form"),
    path("gui/", views.contribution_submit_view, name="submit"),
]
