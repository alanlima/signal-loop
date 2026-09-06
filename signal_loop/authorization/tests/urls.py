from django.http import HttpResponse
from django.urls import include, path

from signal_loop.authorization.decorators import require_permission
from signal_loop.authorization.permissions import Permission


def payload(request, **kwargs):
    return HttpResponse("Authorized synthetic payload")


urlpatterns = [path("", include("signal_loop.urls"))]
for action in Permission:
    route = f"probe/<int:organisation_id>/<int:project_id>/{action.value}/"
    if action == Permission.ADMINISTER_ORGANISATION:
        route = f"probe/<int:organisation_id>/{action.value}/"
    urlpatterns.append(path(route, require_permission(action)(payload)))
