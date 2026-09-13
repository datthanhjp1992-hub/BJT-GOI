"""Root '/' route -> redirect to dashboard (kept separate from urls.py
so config/urls.py can mount it at the site root without a prefix)."""
from django.urls import path
from django.views.generic import RedirectView

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="learning:dashboard"), name="home"),
]
