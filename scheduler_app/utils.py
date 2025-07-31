# scheduler_app/utils.py

def generate_username(socialaccount):
    """
    This is called by allauth to generate a username.
    We will force it to use the user's verified email address.
    """
    # The user object is linked to the socialaccount instance
    return socialaccount.user.email