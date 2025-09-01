# master_calendar/settings.py

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = 'django-insecure-x=x9v&fd!cmw=tdu_po@a^fpb**$e!o1%7y-kipn^)6mlr$xh)'
DEBUG = True
# NGROK_URL= 'https://9d09244585ce.ngrok-free.app'


# ALLOWED_HOSTS = [
#     'localhost',
#     '127.0.0.1',
#     '9d09244585ce.ngrok-free.app',
# ]

# CSRF_TRUSTED_ORIGINS = [
#     'https://9d09244585ce.ngrok-free.app',
#     'https://*.ngrok-free.app',
# ]


# --- Application definition ---

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third Party Apps
    'rest_framework',
    'rest_framework.authtoken',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'allauth.socialaccount.providers.microsoft',
    'channels',

    # Our App
    'scheduler_app.apps.SchedulerAppConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'scheduler_app.middleware.TimezoneMiddleware',  
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
            ],
        },
    },
]

ASGI_APPLICATION = 'master_calendar.asgi.application'
CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer',},
}

# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'db_name',
#         'USER': 'db_user',
#         'PASSWORD': 'user_pass',
#         'HOST': 'localhost', 'PORT': '5432',
#     }
# }

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# --- Internationalization ---
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# --- Static files ---
STATIC_URL = '/static/'
STATICFILES_DIRS = [ BASE_DIR / 'static', ]
STATIC_ROOT = BASE_DIR / 'staticfiles' 
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =======================================================================
# == ALLAUTH & AUTHENTICATION SETTINGS ==================================
# =======================================================================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# --- Redirects ---
LOGIN_REDIRECT_URL = 'redirect_after_login'
LOGOUT_REDIRECT_URL = '/' 
ACCOUNT_LOGOUT_ON_GET = True # Optional: allows logout without a confirmation page

# --- Core Account Settings ---
ACCOUNT_AUTHENTICATION_METHOD = "username_email"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none' # Change to 'mandatory' for production
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = True
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = True


ACCOUNT_ADAPTER = 'allauth.account.adapter.DefaultAccountAdapter'
SOCIALACCOUNT_ADAPTER = 'scheduler_app.adapter.CustomSocialAccountAdapter'


# --- Social Account Settings ---
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
            'https://www.googleapis.com/auth/calendar',
        ],
        'AUTH_PARAMS': {
            'access_type': 'offline',
            'prompt': 'consent',
        }
    },
    'microsoft': {
        'SCOPE': [
            'User.Read',
            'Calendars.ReadWrite',
            'offline_access',
        ],
        'AUTH_PARAMS': {
            'prompt': 'consent',
        }
    }
}
SOCIALACCOUNT_STORE_TOKENS = True


# --- REST FRAMEWORK ---
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
}


# --- EMAIL CONFIGURATION ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtppro.zoho.com'  
EMAIL_PORT = 587  
EMAIL_USE_TLS = True
EMAIL_HOST_USER='hostuser'
EMAIL_HOST_PASSWORD = 'password' 
DEFAULT_FROM_EMAIL = f"Master Calendar <{EMAIL_HOST_USER}>"


# --- LOGGING ---
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



