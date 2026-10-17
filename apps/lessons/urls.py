from django.urls import path

from . import views

app_name = "lessons"

urlpatterns = [
    path("", views.index_view, name="index"),                                    # L1
    path("lich-su/", views.polite_view, name="polite"),                          # L4
    path("lich-su/tra-loi/", views.polite_answer_view, name="polite_answer"),
]
