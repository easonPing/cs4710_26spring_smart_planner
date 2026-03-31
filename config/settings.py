import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def get_env(name, default=None, cast=str):
    value = os.getenv(name, default)
    if value is None:
        return None
    if cast is bool:
        return str(value).lower() in {'1', 'true', 'yes', 'on'}
    if cast is int:
        return int(value)
    return value


def build_logging_config(base_dir: Path):
    logs_dir = base_dir / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    formatter = {
        'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    }
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {'standard': formatter},
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'standard',
            },
            'app_file': {
                'class': 'logging.FileHandler',
                'filename': logs_dir / 'app.log',
                'formatter': 'standard',
            },
            'scheduler_file': {
                'class': 'logging.FileHandler',
                'filename': logs_dir / 'scheduler.log',
                'formatter': 'standard',
            },
            'llm_file': {
                'class': 'logging.FileHandler',
                'filename': logs_dir / 'llm.log',
                'formatter': 'standard',
            },
            'oauth_file': {
                'class': 'logging.FileHandler',
                'filename': logs_dir / 'oauth.log',
                'formatter': 'standard',
            },
        },
        'loggers': {
            'planner': {'handlers': ['console', 'app_file'], 'level': 'INFO'},
            'planner.scheduler': {
                'handlers': ['console', 'scheduler_file'],
                'level': 'INFO',
                'propagate': False,
            },
            'planner.llm': {
                'handlers': ['console', 'llm_file'],
                'level': 'INFO',
                'propagate': False,
            },
            'planner.oauth': {
                'handlers': ['console', 'oauth_file'],
                'level': 'INFO',
                'propagate': False,
            },
        },
    }


SECRET_KEY = get_env('SECRET_KEY', 'django-insecure-smart-planner-dev-key')
DEBUG = get_env('DEBUG', True, bool)
ALLOWED_HOSTS = [host.strip() for host in get_env('ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if host.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'planner',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = 'en-us'
TIME_ZONE = get_env('TIME_ZONE', 'America/New_York')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'planner' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SLOT_MINUTES = get_env('PLANNER_SLOT_MINUTES', 30, int)
RECURRING_HORIZON_DAYS = get_env('PLANNER_RECURRING_HORIZON_DAYS', 84, int)
CODEX_AUTH_PATH = get_env('CODEX_AUTH_PATH', '')
CODEX_CACHE_DIR = BASE_DIR / get_env('CODEX_CACHE_DIR', 'data/oauth_cache')
CODEX_MODEL = get_env('CODEX_MODEL', 'gpt-5.4')
CODEX_API_BASE = get_env('CODEX_API_BASE', 'https://chatgpt.com/backend-api')

for relative_dir in [
    'media/ics',
    'media/syllabi',
    'media/extracted_text',
    'media/task_json',
    'media/schedule_exports',
    'media/temp',
    'data/oauth_cache',
    'data/schedule_versions',
    'data/conflict_reports',
    'data/metrics_exports',
    'data/debug_snapshots',
    'logs',
    'fixtures',
]:
    (BASE_DIR / relative_dir).mkdir(parents=True, exist_ok=True)

LOGGING = build_logging_config(BASE_DIR)
