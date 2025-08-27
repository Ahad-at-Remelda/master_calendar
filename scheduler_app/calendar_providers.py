# scheduler_app/calendar_providers.py

# =======================================================================
# == STEP 3 FIX: Corrected the import statements ========================
# =======================================================================
from allauth.socialaccount.models import SocialAccount, SocialToken
from .models import SyncedCalendar
# =======================================================================

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import requests
import logging

logger = logging.getLogger(__name__)

def discover_and_store_calendars(user):
    """
    Fetches all calendars from all connected social accounts for a user
    and stores them in the SyncedCalendar model. This is the main entry point.
    """
    social_accounts = SocialAccount.objects.filter(user=user)
    
    for acc in social_accounts:
        if acc.provider == 'google':
            _fetch_google_calendars(acc)
        elif acc.provider in ['microsoft', 'MasterCalendarClient']:
            _fetch_microsoft_calendars(acc)

def _fetch_google_calendars(social_acc):
    """Fetches a list of calendars from a specific Google account."""
    try:
        token = SocialToken.objects.get(account=social_acc)
        creds = Credentials(
            token=token.token, refresh_token=token.token_secret,
            token_uri='https://oauth2.googleapis.com/token',
            client_id=token.app.client_id, client_secret=token.app.secret
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            token.token = creds.token
            token.save()

        service = build('calendar', 'v3', credentials=creds)
        calendar_list = service.calendarList().list().execute()

        for calendar_item in calendar_list.get('items', []):
            # We only want to sync calendars the user can write to.
            if calendar_item.get('accessRole') in ['owner', 'writer']:
                SyncedCalendar.objects.update_or_create(
                    user=social_acc.user,
                    social_account=social_acc,
                    calendar_id=calendar_item['id'],
                    defaults={
                        'name': calendar_item['summary'],
                        'provider': 'google',
                        'is_primary': calendar_item.get('primary', False)
                    }
                )
        logger.info(f"Successfully discovered Google calendars for {social_acc.user.username}")
    except Exception as e:
        logger.error(f"Failed to fetch Google calendars for {social_acc.uid}: {e}")

def _fetch_microsoft_calendars(social_acc):
    """Fetches a list of calendars from a specific Microsoft account."""
    try:
        token = SocialToken.objects.get(account=social_acc)
        headers = {'Authorization': f'Bearer {token.token}'}
        response = requests.get('https://graph.microsoft.com/v1.0/me/calendars', headers=headers)
        response.raise_for_status()
        
        for calendar_item in response.json().get('value', []):
            # We only want calendars the user can edit.
            if calendar_item.get('canEdit', False):
                SyncedCalendar.objects.update_or_create(
                    user=social_acc.user,
                    social_account=social_acc,
                    calendar_id=calendar_item['id'],
                    defaults={
                        'name': calendar_item['name'],
                        'provider': 'microsoft',
                        'is_primary': calendar_item.get('isDefaultCalendar', False)
                    }
                )
        logger.info(f"Successfully discovered Microsoft calendars for {social_acc.user.username}")
    except Exception as e:
        logger.error(f"Failed to fetch Microsoft calendars for {social_acc.uid}: {e}")