# --- EMAIL CONFIGURATION ---
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtppro.zoho.com'  
EMAIL_PORT = 587  
EMAIL_USE_TLS = True
EMAIL_HOST_USER='host'
EMAIL_HOST_PASSWORD = 'password'
DEFAULT_FROM_EMAIL = f"Lets Sync <{EMAIL_HOST_USER}>"


DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'db_name',
        'USER': 'user_name',
        'PASSWORD': 'pass',
        'HOST': 'localhost', 'PORT': '5432',
    }
}

NGROK_URL= 'NGROK URL'
SERVER_URL= 'Lets Sync url'  

#edited the letsync url
ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS = ['*']