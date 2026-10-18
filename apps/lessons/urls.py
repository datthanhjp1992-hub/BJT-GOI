from django.urls import path

from . import views

app_name = "lessons"

urlpatterns = [
    path("", views.index_view, name="index"),                                    # L1
    path("<int:scene_no>/thay-the/", views.drill_view, name="drill"),               # L2
    path("<int:scene_no>/thay-the/cham/", views.drill_mark_view, name="drill_mark"),
    path("chuong/<int:unit_no>/dong-vai/<int:number>/", views.roleplay_view, name="roleplay"),  # L3
    path("chuong/<int:unit_no>/dong-vai/<int:number>/cham/", views.roleplay_mark_view, name="roleplay_mark"),
    path("lich-su/", views.polite_view, name="polite"),                          # L4
    path("lich-su/tra-loi/", views.polite_answer_view, name="polite_answer"),
]
