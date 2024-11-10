import os
import json
from pathlib import Path
from jsonschema import validate, ValidationError

def jsonSerializer(data: str):
    return json.dumps(data, indent=2)

def jsonDeSerializer(data: str):
    return json.loads(data)

def loadJSONSchema(filePath: str):
    relative_path = filePath

    # Get the absolute path
    file_path = Path(relative_path)

    # Load the file using the absolute path
    try:
        with open(file_path, 'r') as file:
            content = file.read()
            return json.loads(content)
    except FileNotFoundError:
        print(f"File not found: {file_path}")
    except Exception as e:
        print(f"An error occurred: {e}")

def jsonSchemaValidate(schema: dict, json_message: dict):
    try:
        # Parse the JSON message
        data = json.loads(json_message)

        # Validate against the schema
        validate(instance=data, schema=schema)

        print("Validation successful. Message is valid against the schema.")
        return True
    except ValidationError as e:
        print(f"Validation error: {e}")
        return False