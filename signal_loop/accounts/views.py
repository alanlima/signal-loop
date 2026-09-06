from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from signal_loop.navigation import render_shell


class SignInView(LoginView):
    template_name = "accounts/login.html"

    def get_redirect_url(self):
        target = super().get_redirect_url()
        # Accept only local absolute paths, even when a same-host URL would be safe.
        if (
            not target.startswith("/")
            or target.startswith("//")
            or "\\" in target
            or any(ord(character) < 32 or ord(character) == 127 for character in target)
        ):
            return ""
        return target


class SignOutView(LogoutView):
    def get_redirect_url(self):
        # Logout always lands on the public login page, regardless of submitted next.
        return ""


@login_required
def application_entry(request):
    return render_shell(request)


@login_required
def shell_destination(request, destination):
    return render_shell(request, destination)
