import requests
import os

import logging

# Set up a logger
logger = logging.getLogger("authentication_module_logger")
logger.setLevel(logging.DEBUG)  # Set the minimum logging level to DEBUG

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Set handler-specific level

# Create a file handler
file_handler = logging.FileHandler("authentication_module_app.log")
file_handler.setLevel(logging.DEBUG)

# Define a log message format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)
permission_url = os.getenv("PERMISSIONS_URL")

class JWT:
    def __init__(self):
        self.is_bearer_token = True

    @staticmethod
    def get_user_id_from_token(bearer_token):
        path_for_authentication = "/api/v1/users/uservalidation"
        url = permission_url + path_for_authentication
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }
        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("employeeId", None)
            else:
                logger.error(f"Failed: {response.status_code}, {response.text}")
                return ""
        except requests.exceptions.RequestException as e:
            return f"Error: {e}"