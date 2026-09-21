from django.urls import path

from . import views

app_name = "gamification"

urlpatterns = [
    path("", views.contribution_view, name="form"),
    path("gui/", views.contribution_submit_view, name="submit"),
    # SC13 Điểm & Thành tích — nằm chung app với Góp ý vì điểm/danh hiệu sinh
    # ra từ chính luồng góp ý (xem docs/SPEC_GOP_Y_THANH_TICH.md).
    path("thanh-tich/", views.achievements_view, name="achievements"),
    # Ghim/bỏ ghim là POST (có đổi dữ liệu) và định danh nhóm danh hiệu bằng
    # code_type — khoá nghiệp vụ của BadgeCategory, ổn định hơn pk khi seed
    # lại dữ liệu ở môi trường khác.
    path("thanh-tich/ghim/<str:code_type>/", views.pin_badge_view, name="pin_badge"),
    path("thanh-tich/bo-ghim/<str:code_type>/", views.unpin_badge_view, name="unpin_badge"),
]
