# AppleHealthDashboard-v2
This takes data from an Apple watch, saves it into a database and then serves a webserver local on port 8080 - Now with upload fuction.

#Get data from iPhone

Go into  the Health app - Select your Profile - Select Export all data and save the ZIP file

WARNING: This can be multiple GB even as ZIP




#Install python and dependencies

Python depends on your OS - This was tested on Linux

Windows: py -m pip install Flask

MacOS/Linux: pip3 install Flask waitress

Linux Debian: apt install python3 python3-flask python3-waitress

#Save the script in a local directory, keep the structure as in the repository



#Start, Automatically binds on port 880 on all IPs

Linux: python3 app.py


#Visit Webserver and upload your ZIP file (can be done directly from iPhone), this will start the import and redirect you to the Dashboard

http://127.0.0.1:8080/upload




