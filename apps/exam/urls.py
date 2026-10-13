from django.urls import path

from . import views

app_name = "exam"

# docs/SPEC_KIEM_TRA.md mục 1.4. Mốc 1: S1, S2, S3. Mốc 2: S4–S7. Mốc 3: S8.
urlpatterns = [
    path("", views.hub_view, name="hub"),                                              # S1
    path("tu-vung/", views.vocab_setup_view, name="vocab"),                            # S2
    path("de-thi/", views.exam_list_view, name="exams"),                               # S4
    path("de-thi/<slug:set_slug>/bat-dau/", views.start_mock_view, name="start_mock"),
    path("dang-de/<slug:section_code>/bat-dau/", views.start_drill_view, name="start_drill"),
    path("so-cau-sai/", views.wrongbook_view, name="wrongbook"),                       # S8
    path("so-cau-sai/on/<slug:target>/", views.start_wrongbook_view, name="start_wrongbook"),
    path("luot/<int:attempt_id>/", views.play_view, name="play"),                      # S3 / S5 / S6
    path("luot/<int:attempt_id>/nop-phan/", views.submit_part_view, name="submit_part"),
    path("luot/<int:attempt_id>/nop/", views.finish_view, name="finish"),
    path("luot/<int:attempt_id>/bo/", views.abandon_view, name="abandon"),
    path("luot/<int:attempt_id>/lam-lai/", views.restart_view, name="restart"),
    path("luot/<int:attempt_id>/ket-qua/", views.result_view, name="result"),          # S7
    path("luot/<int:attempt_id>/them-tu/", views.add_words_view, name="add_words"),
]
