# master_calendar/settings.py

import os
from pathlib import Path
import os
# Unused variables from the top have been removed for clarity
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-x=x9v&fd!cmw=tdu_po@a^fpb**$e!o1%7y-kipn^)6mlr$xh)'
DEBUG = True
NGROK_URL= 'https://29eee4c780a5.ngrok-free.app'

# --- THIS IS THE CRITICAL FIX ---
# Hostnames must NOT include 'http://' or 'https://'.
# The '.ngrok-free.app' entry is a wildcard that will match any ngrok subdomain.
ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '29eee4c780a5.ngrok-free.app',
]
# --------------------------------
CSRF_TRUSTED_ORIGINS = [
    'https://29eee4c780a5.ngrok-free.app',
    'https://*.ngrok-free.app',
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'rest_framework',
    'rest_framework.authtoken',
    # Third-Party Apps (Second)
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.microsoft',
    'channels',

    # Your Local Apps (Last)
    'scheduler_app.apps.SchedulerAppConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'master_calendar.urls'
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
                'django.template.context_processors.request',
            ],
        },
    },
]

ASGI_APPLICATION = 'master_calendar.asgi.application'
CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer',},
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'master_calendar_db',
        'USER': 'master_user',
        'PASSWORD': 'master_pass',
        'HOST': 'localhost', 'PORT': '5432',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
SITE_ID = 1


SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile', 'email', 'https://www.googleapis.com/auth/calendar.readonly', 'https://www.googleapis.com/auth/calendar.events',
        ],
        'AUTH_PARAMS': {'access_type': 'offline'}
    },
    'microsoft': {
        'SCOPE': ['User.Read', 'Calendars.ReadWrite', 'offline_access'],
    }
}

SOCIALACCOUNT_USERNAME_GENERATOR = 'scheduler_app.utils.generate_username'
SOCIALACCOUNT_AUTO_SIGNUP = True
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler',},},
    'root': {'handlers': ['console'], 'level': 'INFO',},
}

SOCIALACCOUNT_STORE_TOKENS = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
ACCOUNT_EMAIL_VERIFICATION = 'none'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

SOCIALACCOUNT_ADAPTER = 'scheduler_app.adapter.CustomSocialAccountAdapter'
LOGIN_REDIRECT_URL = 'redirect_after_login'
LOGOUT_REDIRECT_URL = '/' 

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}
