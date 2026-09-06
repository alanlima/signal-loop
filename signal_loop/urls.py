from django.urls import path

from signal_loop.views import home

urlpatterns = [path("", home, name="home")]
