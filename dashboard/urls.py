from django.urls import path
from django.contrib.auth import views as auth
from inventory import views
urlpatterns = [path("telemetry/",views.overview,name="overview"),path("telemetry/devices/<int:device_id>/",views.device,name="device"),path("telemetry/login/",auth.LoginView.as_view(template_name="registration/login.html"),name="login"),path("telemetry/logout/",auth.LogoutView.as_view(),name="logout"),path("telemetry/password/",auth.PasswordChangeView.as_view(template_name="registration/password.html",success_url="/telemetry/"),name="password"),path("telemetry/healthz/",views.healthz,name="healthz")]
