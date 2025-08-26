# master_calendar

Steps:

copy proto_settings -> create settings.py -> Commented part update 

setup ngrok server 

add: ngrok url , crsf token and allowed hosts

add postgres db settings (create db add into)

pip install requirements.txt

python manage.py makemigrations

python manage.py migrate

create superuser

terminal 1 : run ngrok ( ngrok http 8000 ) 

terminal 2 : daphne -p 8000 master_calendar.asgi:application


change required:
settings-> allowedhosts,crsf trusted token,ngrk url
.env
everytime....

