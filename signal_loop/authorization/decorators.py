from functools import wraps

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpResponse
from django.shortcuts import resolve_url

from .permissions import has_permission


def require_permission(permission):
    """Use organisation_id/project_id from the resolved URL, never submitted claims."""
    def decorate(view):
        @wraps(view)
        def guarded(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), resolve_url(settings.LOGIN_URL))
            if not has_permission(
                request.user, permission,
                organisation_id=kwargs.get("organisation_id"),
                project_id=kwargs.get("project_id"),
            ):
                return HttpResponse("Not found.", status=404, content_type="text/plain")
            return view(request, *args, **kwargs)
        return guarded
    return decorate
