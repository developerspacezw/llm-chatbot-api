import os
import asyncio
import requests
import uuid
from statistics import correlation

import websockets

import json
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka import Producer, Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import StringSerializer, StringDeserializer
from websockets.exceptions import InvalidHandshake
from dotenv import load_dotenv

import logging

# Set up a logger
logger = logging.getLogger("websocket_llm_logger")
logger.setLevel(logging.DEBUG)  # Set the minimum logging level to DEBUG

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Set handler-specific level

# Create a file handler
file_handler = logging.FileHandler("websocket_app.log")
file_handler.setLevel(logging.DEBUG)

# Define a log message format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)


load_dotenv()

# Load environment variables
bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")
permission_url = os.getenv("PERMISSIONS_URL")


# Kafka producer and consumer configuration
producer_config = {
    "bootstrap.servers": bootstrap_server_url,
}

consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "websocket_group",
    "auto.offset.reset": "earliest",
}

# Kafka producer and consumer configuration
schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})

# Define serializers and deserializers
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(schema_registry_client, schema_str=open('./schemas/avro/llm.avsc').read())

key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(schema_registry_client, schema_str=open('./schemas/avro/llm.avsc').read())

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
            logger.info(data.get("employeeId", None))
            return data.get("employeeId", None)
        else:
            logger.error(f"Failed: {response.status_code}, {response.text}")
            return ""
    except requests.exceptions.RequestException as e:
        return f"Error: {e}"

def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")


def produce(Incoming_request, message_type, user_id, correlation_id):
    """Produce a message to the Kafka topic using Avro schema"""
    producer = Producer(producer_config)
    genuuid = str(uuid.uuid4())
    value = {
        "uuid": genuuid,
        "request": Incoming_request,
        "requestType": message_type,
        "response": ""
    }

    # Create a serialization context for the value
    value_ctx = SerializationContext(llm_topic_request, MessageField.VALUE)

    # Serialize and send message
    try:
        producer.produce(
            topic=llm_topic_request,
            key=key_serializer(genuuid, SerializationContext(llm_topic_request, MessageField.KEY)),
            value=value_serializer(value, value_ctx),
            on_delivery=delivery_report,
            headers={
                "user_id": user_id,
                "correlation_id": correlation_id,
                "reply_to": llm_topic_response
            }
        )
        # Log the message before producing
        logger.info(
            f"Producing message to topic: {llm_topic_request}, "
            f"Key: {genuuid}, Value: {value}, Headers: {{'correlation_id': {genuuid}, 'reply_to': {llm_topic_response}}}"
        )
        producer.poll(1000)
        producer.flush()
    except KafkaException as e:
        logger.error(f"Failed to produce message: {e}")
    finally:
        producer.flush()


def consume(target_correlation_id, target_user_id):
    consumer = Consumer(consumer_config)
    consumer.subscribe([llm_topic_response])

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaException:
                    continue
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                    break

            # Deserialize the Avro message
            headers = {header[0]: header[1].decode() for header in (msg.headers() or [])}

            # Filter by correlation_id and user_id
            __correlation_id = headers.get("correlation_id")
            user_id = headers.get("user_id")  # Assuming user_id is sent in headers

            if __correlation_id == target_correlation_id and user_id == target_user_id:
                key = key_deserializer(msg.key(), SerializationContext(llm_topic_response, MessageField.KEY))
                value = value_deserializer(msg.value(), SerializationContext(llm_topic_response, MessageField.VALUE))

                logger.info(
                    f"Filtered message: Key: {key}, Value: {value}, Headers: {headers}"
                )
                return value["response"]

            logger.debug(f"Skipped message with Headers: {headers}")

        return "No matching response found"
    except KeyboardInterrupt:
        logger.warning("Consumer interrupted by user")
    finally:
        consumer.close()


logger.info("Starting WebSocket server")


async def generate(websocket):
    # Extract Bearer Token from WebSocket headers
    token = websocket.request_headers.get("Authorization")

    if not token or not token.startswith("Bearer "):
        # Close connection if token is missing or invalid
        await websocket.close(code=4000, reason="Missing or invalid Authorization header")
        return

    # Remove 'Bearer ' prefix to extract the token value
    token = token[len("Bearer "):].strip()
    logger.info(f"User Bearer Token: {token}")
    # Validate the token and get the user ID
    user_id = get_user_id_from_token(token)
    logger.info(f"User ID :: {user_id}")
    if user_id == "":
        await websocket.close(code=4001, reason="Unauthorized or invalid token")
        return

    # Process incoming messages
    while True:
        try:
            # Receive message body
            input_message = await websocket.recv()
            correlation_id = str(uuid.uuid4())
            # Produce a request to Kafka
            produce(input_message, "request", user_id=user_id, correlation_id=correlation_id)

            # Consume the response for the specific user ID
            output_text = consume(target_user_id=user_id, target_correlation_id=correlation_id)

            # Send back the response
            await websocket.send(output_text)
        except Exception as e:
            # Log the error and notify the client
            logger.error(f"Error during message processing: {str(e)}")
            await websocket.send(json.dumps({"error": "An error occurred during processing"}))
            break

async def main():
    async with websockets.serve(generate, "", 8001):
        logger.info(f"Authentication URL :: {permission_url}")
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())