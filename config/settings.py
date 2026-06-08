import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_str(name: str, default: str = '') -> str:
    value = os.getenv(name, default)
    if value is None:
        return default
    return value.strip().strip('"').strip("'")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = env_str(name)
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(',') if item.strip()]


SECRET_KEY = env_str('SECRET_KEY')
DEBUG = env_bool('DEBUG', False)

if not DEBUG and not SECRET_KEY:
    raise ImproperlyConfigured('SECRET_KEY обязателен при DEBUG=False.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', ['localhost', '127.0.0.1'])
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core.apps.CoreConfig',
    'apps.references',
    'apps.composites',
    'apps.materials',
    'apps.samples',
    'apps.scans',
    'apps.structures',
]

if DEBUG:
    INSTALLED_APPS.append('debug_toolbar')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

if DEBUG:
    MIDDLEWARE.append('debug_toolbar.middleware.DebugToolbarMiddleware')

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.tag_suggestions',
            ],
            'libraries': {
                'ui_tags': 'apps.core.templatetags.ui_tags',
            },
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

FORM_RENDERER = 'django.forms.renderers.DjangoTemplates'

if env_str('DB_ENGINE').lower() == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env_str('DB_NAME', 'composites_db'),
            'USER': env_str('DB_USER'),
            'PASSWORD': env_str('DB_PASSWORD'),
            'HOST': env_str('DB_HOST', 'localhost'),
            'PORT': env_str('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Большие HDF5-файлы (до 20 ГБ) не держим целиком в памяти — пишем во временный файл.
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# Загружаемые файлы: S3 (если USE_S3=true и задан bucket) или локальная папка media/.
AWS_ACCESS_KEY_ID = env_str('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = env_str('AWS_SECRET_ACCESS_KEY')
AWS_STORAGE_BUCKET_NAME = env_str('AWS_STORAGE_BUCKET_NAME')
AWS_S3_ENDPOINT_URL = env_str('AWS_S3_ENDPOINT_URL')
AWS_S3_REGION_NAME = env_str('AWS_S3_REGION_NAME', 'us-east-1')
AWS_S3_ADDRESSING_STYLE = env_str('AWS_S3_ADDRESSING_STYLE', 'path')
AWS_S3_SIGNATURE_VERSION = env_str('AWS_S3_SIGNATURE_VERSION', 's3v4')

USE_S3_STORAGE = env_bool('USE_S3', default=bool(AWS_STORAGE_BUCKET_NAME))

if USE_S3_STORAGE:
    if not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured(
            'USE_S3=true, но AWS_STORAGE_BUCKET_NAME не задан.'
        )

    INSTALLED_APPS.append('storages')
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 3600
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_VERIFY = env_bool('AWS_S3_VERIFY', default=AWS_S3_ENDPOINT_URL.startswith('https://'))
    AWS_S3_USE_SSL = AWS_S3_ENDPOINT_URL.startswith('https://') if AWS_S3_ENDPOINT_URL else True
    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
            'OPTIONS': {
                'location': MEDIA_ROOT,
                'base_url': MEDIA_URL,
            },
        },
        'staticfiles': {
            'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage',
        },
    }

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SECURE = env_bool('SESSION_COOKIE_SECURE', False)
    CSRF_COOKIE_SECURE = env_bool('CSRF_COOKIE_SECURE', False)
    if env_bool('SECURE_SSL_REDIRECT', False):
        SECURE_SSL_REDIRECT = True

INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]
