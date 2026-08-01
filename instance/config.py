import os

SECRET_KEY = os.environ["SECRET_KEY"]

def _env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

MAIL_SERVER = os.environ["MAIL_SERVER"]
MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
MAIL_USE_TLS = _env_bool("MAIL_USE_TLS", False)
MAIL_USE_SSL = _env_bool("MAIL_USE_SSL", False)
MAIL_USERNAME = os.environ["MAIL_USERNAME"]
MAIL_PASSWORD = os.environ["MAIL_PASSWORD"]
MAIL_DEFAULT_SENDER = os.environ["MAIL_USERNAME"]

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
