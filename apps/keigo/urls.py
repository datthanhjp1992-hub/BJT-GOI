from django.urls import path

from . import views

app_name = "keigo"

urlpatterns = [
    path("", views.index_view, name="index"),  # SC16
    path("tra-cuu/", views.verb_lookup_view, name="tra_cuu"),  # SC18
    path("tra-cuu/<int:pk>/", views.verb_detail_view, name="verb_detail"),
    path("hoc/", views.learn_start_view, name="hoc"),  # muc "Hoc tu" o sidebar
    # SC19 -- PHAI dung TRUOC <slug:slug>/ ben duoi, neu khong bi lesson_view nuot (404).
    path("loi-thuong-gap/", views.pitfall_view, name="loi_thuong_gap"),
    # SC20-SC22 -- bai tap. Cung PHAI dung TRUOC <slug:slug>/.
    path("bai-tap/", views.exercise_list_view, name="bai_tap"),  # SC20
    path("bai-tap/<slug:set_slug>/", views.exercise_play_view, name="bai_tap_lam"),  # SC21
    path("bai-tap/<slug:set_slug>/bat-dau/", views.exercise_start_view, name="bai_tap_bat_dau"),
    path("bai-tap/<slug:set_slug>/bo/", views.exercise_abandon_view, name="bai_tap_bo"),
    path("bai-tap/<slug:set_slug>/nop/", views.exercise_finish_view, name="bai_tap_nop"),
    path("bai-tap/<slug:set_slug>/ket-qua/", views.exercise_result_view, name="bai_tap_ket_qua"),  # SC22
    path("<slug:slug>/pdf/", views.lesson_pdf_view, name="lesson_pdf"),  # SC17 nut in on tap
    # SC17 -- DE CUOI CUNG: <slug:slug> khop moi chuoi slug, ke ca "tra-cuu"/"hoc".
    path("<slug:slug>/", views.lesson_view, name="lesson"),
]
