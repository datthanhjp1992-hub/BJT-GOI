"""
Makes the current request's user available inside model.save(), so
AuditableModel can auto-fill created_by / updated_by without every
view having to pass the user explicitly.
"""
import threading

_thread_locals = threading.local()


def get_current_user():
    return getattr(_thread_locals, "user", None)


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _thread_locals.user = getattr(request, "user", None)
        try:
            response = self.get_response(request)
        finally:
            _thread_locals.user = None
        return response
