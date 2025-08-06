# master_calendar

pip install requirements.txt


terminal 1 : run ngrok ( ngrok http 8000 ) 

terminal 2 : daphne master_calendar.asgi:application

daphne -p 8000 master_calendar.asgi:application

change required:
settings-> allowedhosts,crsf trusted token
googleConsole-> https://1070c35f0614.ngrok-free.app/accounts/google/login/callback/
also in signals.py 
.env
everytime....


https://1070c35f0614.ngrok-free.app 
 
https://1070c35f0614.ngrok-free.app /register-google-watch/
