# master_calendar/settings.py

"""
Django settings for master_calendar project.
"""
import os

from pathlib import Path

GOOGLE_CLIENT_ID = '953117850503-6u8fs8iqb3h7irkvqrtiivkn1leti9td.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET = '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'
GOOGLE_REDIRECT_URI = "http://localhost:8000"
GOOGLE_SCOPE = "https://www.googleapis.com/auth/calendar"


# calendar_project/settings.py


# Add these variables (replace with your own)

# Templates
#TEMPLATES[0]['DIRS'] = [BASE_DIR / 'calendar_app' / 'templates']




# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-x=x9v&fd!cmw=tdu_po@a^fpb**$e!o1%7y-kipn^)6mlr$xh)'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
    '59faa4998f9e.ngrok-free.app',  # <-- your ngrok domain here
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Your app
    'scheduler_app',
    
    # Allauth apps
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google', 
    'allauth.socialaccount.providers.microsoft', # <-- ADD THIS LINE

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
        'DIRS': [],
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

WSGI_APPLICATION = 'master_calendar.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'master_calendar_db',
        'USER': 'master_user',
        'PASSWORD': 'master_pass',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ==============================================================================
# FINAL, CORRECT ALLAUTH AND AUTHENTICATION CONFIGURATION
# ==============================================================================

# This tells Django to use both its own login system (for admin) and allauth's.
# This was a critical missing piece.
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1 # Required by allauth

# This tells allauth to redirect to the home page after login/logout.
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Provider-specific settings (e.g., for Google)
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
            'https://www.googleapis.com/auth/calendar.readonly',
            'https://www.googleapis.com/auth/calendar.events',
        ],
        'AUTH_PARAMS': {
            'access_type': 'offline',
        }
    },
     'microsoft': {
        'SCOPE': [
            'User.Read',
            'Calendars.ReadWrite', # Permission to read and write to calendars
            'offline_access',      # Allows getting a refresh token
        ],
    }
}

# This forces the username to be created from the email, using a custom function.
# This is the fix for the "abdul" username conflict.
SOCIALACCOUNT_USERNAME_GENERATOR = 'scheduler_app.utils.generate_username'

# This ensures users are created automatically from Google without extra steps.
SOCIALACCOUNT_AUTO_SIGNUP = True

# This handles modern login and email requirements correctly.
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_UNIQUE_EMAIL = True
# ==============================================================================
# END OF CONFIGURATION
# ==============================================================================

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
        'level': 'INFO', # You can change this to 'DEBUG' for even more detail
    },
}

SOCIALACCOUNT_STORE_TOKENS = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True