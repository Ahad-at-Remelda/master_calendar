# scheduler_app/__init__.py

# scheduler_app/__init__.py

default_app_config = 'scheduler_app.apps.SchedulerAppConfig'

### **The Final, Automated Workflow**

# You were right. The manual command is dead. The complex `apps.py` script is dead. This new, event-driven system is the correct way.

# 1.  **Delete** the old, failed `scheduler_app/apps.py` file.
# 2.  **Delete** the old `scheduler_app/management/commands/register_google_webhook.py` file.
# 3.  **Create** the new `scheduler_app/signals.py` file with the code above.
# 4.  **Add** the import line to your `scheduler_app/__init__.py` file.
# 5.  **Restart** your server: `daphne master_calendar.asgi:application`.

# **Now, test the automation:**

# 1.  Log out of your application.
# 2.  Go to your app's home page in an Incognito window.
# 3.  **Watch your Daphne terminal.**
# 4.  Click **"Login with Google"**.
# 5.  After you successfully log in and are redirected back to the home page, **look at your terminal logs**.

# You will see the new log messages from `signals.py` appear **automatically**: