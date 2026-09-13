"""Injects the current user's chosen theme into every template context,
so base.html can pick the right CSS (theme_a.css / theme_b.css / theme_c.css).
"""


def ui_theme(request):
    theme = "A"
    if request.user.is_authenticated:
        theme = request.user.ui_theme
    return {"ui_theme": theme}
