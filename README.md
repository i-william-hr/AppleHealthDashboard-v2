# AppleHealthDashboard-v2
This takes data from an Apple watch, saves it into a database and then serves a webserver local on port 8080 - Now with upload fuction.

#Get data from iPhone

Go into  the Health app - Select your Profile - Select Export all data and save the ZIP file

WARNING: This can be multiple GB even as ZIP


This version supports HTTP BASIC AUTH, AUTH via Token (to eg. set as Widget on Phone homescreen and not always enter User/PW) and is designed to run behind nginx as reverse proxy, so it only binds to 127.0.0.1

URL AUTH can be used by settig a token in app.py and calling /health/?auth=TOKEN



#Install python and dependencies

Python depends on your OS - This was tested on Linux

Windows: py -m pip install Flask

MacOS/Linux: pip3 install Flask waitress flask-httpauth

Linux Debian: apt install python3 python3-flask python3-waitress python3-flask-httpauth

#Save the script in a local directory, keep the structure as in the repository

#Change your nginx sites-enabled to add the proxy with the example from the sites-enabled in the repo



#Start, Automatically binds on port 8080 on all IPs (can be changed in app.py if needed)

Linux: python3 app.py


#Visit Webserver and upload your ZIP file (can be done directly from iPhone), this will start the import and redirect you to the Dashboard - To update the data simply re-export on your device and re-upload



http://127.0.0.1:8080/upload




