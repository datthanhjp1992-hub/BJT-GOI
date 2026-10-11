from django.urls import path

from . import views

app_name = "exam"

# docs/SPEC_KIEM_TRA.md mục 1.4. Mốc 1: S1, S2, S3 + kết quả bài từ vựng.
urlpatterns = [
    path("", views.hub_view, name="hub"),                                         # S1
    path("tu-vung/", views.vocab_setup_view, name="vocab"),                       # S2
    path("luot/<int:attempt_id>/", views.play_view, name="play"),                 # S3
    path("luot/<int:attempt_id>/nop/", views.finish_view, name="finish"),
    path("luot/<int:attempt_id>/bo/", views.abandon_view, name="abandon"),
    path("luot/<int:attempt_id>/ket-qua/", views.result_view, name="result"),
]
