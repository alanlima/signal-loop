from django.urls import path

from signal_loop.accounts.views import SignInView, SignOutView, application_entry
from signal_loop.membership.admin import site as organisation_admin
from signal_loop.views import home

urlpatterns = [
    path("", home, name="home"),
    path("accounts/login/", SignInView.as_view(), name="login"),
    path("accounts/logout/", SignOutView.as_view(), name="logout"),
    path("app/", application_entry, name="application_entry"),
    path("admin/", organisation_admin.urls),
]
