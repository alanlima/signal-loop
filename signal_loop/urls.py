from django.urls import path

from signal_loop.accounts.views import SignInView, SignOutView, application_entry, shell_destination
from signal_loop.membership.admin import site as organisation_admin
from signal_loop.views import home
from signal_loop.checkins.views import personal_check_in

urlpatterns = [
    path("", home, name="home"),
    path("accounts/login/", SignInView.as_view(), name="login"),
    path("accounts/logout/", SignOutView.as_view(), name="logout"),
    path("app/", application_entry, name="application_entry"),
    path("app/check-in/", personal_check_in, name="current_check_in"),
    path("app/team-reports/", shell_destination, {"destination": "team_reports"}, name="team_reports"),
    path("app/manager-reports/", shell_destination, {"destination": "manager_reports"}, name="manager_reports"),
    path("admin/", organisation_admin.urls),
]
