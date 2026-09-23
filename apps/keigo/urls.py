from django.urls import path

from . import views

app_name = "keigo"

urlpatterns = [
    path("", views.index_view, name="index"),  # SC16
    path("tra-cuu/", views.verb_lookup_view, name="tra_cuu"),  # SC18
    path("tra-cuu/<int:pk>/", views.verb_detail_view, name="verb_detail"),
]
