"""Environment-driven settings for the container deployment."""

import os

from django.core.exceptions import ImproperlyConfigured

from .settings import *  # noqa: F403

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    raise ImproperlyConfigured('DJANGO_SECRET_KEY must be set')

DEBUG = os.environ.get('DJANGO_DEBUG', 'false').lower() == 'true'
ALLOWED_HOSTS = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',') if host.strip()]
# The container health probe uses localhost, even when public hosts are restricted.
ALLOWED_HOSTS += ['localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in (os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS') or 'http://localhost:8080,http://localhost:5173').split(',') if origin.strip()]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('POSTGRES_DB', 'app'),
        'USER': os.environ.get('POSTGRES_USER', 'app'),
        'PASSWORD': os.environ.get('POSTGRES_PASSWORD', ''),
        'HOST': os.environ.get('POSTGRES_HOST', 'db'),
        'PORT': os.environ.get('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': os.environ.get('REDIS_CACHE_URL', 'redis://redis:6379/2'),
        'TIMEOUT': 300,
    },
}

MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')  # noqa: F405
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # noqa: F405
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/1')
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = os.environ.get('BUSINESS_TIME_ZONE', 'Asia/Kolkata')
TIME_ZONE = CELERY_TIMEZONE

# Enable these only behind a trusted TLS-terminating reverse proxy.
SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', 'false').lower() == 'true'
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
if SECURE_SSL_REDIRECT:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.console.EmailBackend',
)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'no-reply@localhost')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'false').lower() == 'true'
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '30'))
BILLING_PERIOD_PRICING_PROVIDER = os.environ.get(
    'BILLING_PERIOD_PRICING_PROVIDER',
    'products.services.billing_adapter.price_subscription_period',
)
