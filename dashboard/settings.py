import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,10.1.96.3,concierge-controller,chcnc-mon").split(",")
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "inventory"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "dashboard.urls"
WSGI_APPLICATION = "dashboard.wsgi.application"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[BASE_DIR/"templates"],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]
def database(name, prefix):
 return {"ENGINE":"django.db.backends.mysql", "NAME":name, "USER":os.environ[prefix+"_USER"], "PASSWORD":os.environ[prefix+"_PASSWORD"], "HOST":os.environ.get(prefix+"_HOST","127.0.0.1"), "PORT":os.environ.get(prefix+"_PORT","3306"), "CONN_MAX_AGE":60, "OPTIONS":{"charset":"utf8mb4","init_command":"SET sql_mode='STRICT_TRANS_TABLES'","connect_timeout":5}}
DATABASES = {"default":database("concierge_dashboard","DASHBOARD_DB"), "telemetry":database("prod_telemetry","INVENTORY_DB"), "icinga":database("icingadb","INVENTORY_DB")}
DATABASE_ROUTERS = ["dashboard.router.ReadOnlyRouter"]
AUTH_PASSWORD_VALIDATORS = [{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},{"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"},{"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"},{"NAME":"django.contrib.auth.password_validation.NumericPasswordValidator"}]
LOGIN_URL = "/telemetry/login/"
LOGIN_REDIRECT_URL = "/telemetry/"
LOGOUT_REDIRECT_URL = LOGIN_URL
STATIC_URL = "/telemetry/static/"
STATIC_ROOT = BASE_DIR/"staticfiles"
STORAGES = {"default":{"BACKEND":"django.core.files.storage.FileSystemStorage"},"staticfiles":{"BACKEND":"whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "America/New_York"
USE_TZ = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_PATH = "/telemetry/"
CSRF_COOKIE_PATH = "/telemetry/"
SESSION_COOKIE_AGE = 28800
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CONTROLLER_URL = "http://127.0.0.1:8080"
MONITOR_TOKEN_FILE = os.environ.get("MONITOR_TOKEN_FILE","/etc/concierge-telemetry-dashboard/monitor.token")
TELEMETRY_STALE_SECONDS = 600

TENANT_UUID = "56837d67-b68e-11f1-8cf6-5a0006aa6c1c"

STATE_ROOT = "/var/lib/telemetry-controller/state"
