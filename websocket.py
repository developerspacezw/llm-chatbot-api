import asyncio
import json
import logging
import os
import urllib.parse
import uuid

import websockets
from confluent_kafka import Consumer, KafkaException, Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer, AvroSerializer
from confluent_kafka.serialization import (
    MessageField,
    SerializationContext,
    StringDeserializer,
    StringSerializer,
)
from dotenv import load_dotenv
from elasticapm import Client
from elasticapm.contrib.asyncio.traces import capture_span
from websockets.exceptions import ConnectionClosedError

import authentication.jwt as auth

# Set up Elastic APM client
apm_client = Client(
    service_name="websocket-llm-service",
    server_url=os.getenv("ELASTIC_APM_SERVER_URL", "http://localhost:8200"),
    environment=os.getenv("ENVIRONMENT", "development"),
    secret_token=os.getenv("ELASTIC_APM_SECRET_TOKEN", ""),
)

# Enable auto instrumentation
apm_client.begin_transaction("custom")
apm_client.end_transaction("initialize", "success")

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
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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
value_serializer = AvroSerializer(
    schema_registry_client, schema_str=open("./schemas/avro/llm.avsc").read()
)

key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(
    schema_registry_client, schema_str=open("./schemas/avro/llm.avsc").read()
)


def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")


def produce(incoming_request, message_type, user_id, correlation_id):
    """Produce a message to the Kafka topic using Avro schema"""
    producer = Producer(producer_config)
    genuuid = str(uuid.uuid4())
    value = {
        "uuid": genuuid,
        "request": incoming_request,
        "requestType": message_type,
        "response": "",
    }

    # Create a serialization context for the value
    value_ctx = SerializationContext(llm_topic_request, MessageField.VALUE)

    # Serialize and send message
    try:
        producer.produce(
            topic=llm_topic_request,
            key=key_serializer(
                genuuid, SerializationContext(llm_topic_request, MessageField.KEY)
            ),
            value=value_serializer(value, value_ctx),
            on_delivery=delivery_report,
            headers={
                "user_id": user_id,
                "correlation_id": correlation_id,
                "reply_to": llm_topic_response,
            },
        )
        # Log the message before producing
        logger.info(
            f"Producing message to topic: {llm_topic_request}, "
            f"Key: {genuuid}, "
            f"Value: {value}, "
            f"Headers: {{'correlation_id': {genuuid}, "
            f"'reply_to': {llm_topic_response}}}"
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
            headers = {
                header[0]: header[1].decode() for header in (msg.headers() or [])
            }

            # Filter by correlation_id and user_id
            __correlation_id = headers.get("correlation_id")
            user_id = headers.get("user_id")  # Assuming user_id is sent in headers

            if __correlation_id == target_correlation_id and user_id == target_user_id:
                key = key_deserializer(
                    msg.key(),
                    SerializationContext(llm_topic_response, MessageField.KEY),
                )
                value = value_deserializer(
                    msg.value(),
                    SerializationContext(llm_topic_response, MessageField.VALUE),
                )

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
    # Extract the path from the request object
    path = websocket.request.path
    logger.info(f"WebSocket connection established at path: {path}")

    # Parse the path to extract query parameters
    parsed_url = urllib.parse.urlparse(path)
    query_params = urllib.parse.parse_qs(parsed_url.query)

    # Extract the token from query parameters
    token_list = query_params.get("token", [None])
    token = token_list[0] if token_list else None

    if not token:
        await websocket.close(code=4000, reason="Missing token in query parameters")
        return

    logger.info(f"User Bearer Token: {token}")

    # Authenticate the user using the token
    user_id = auth.JWT.get_user_id_from_token(token)
    logger.info(f"User ID :: {user_id}")
    if not user_id:
        await websocket.close(code=4001, reason="Unauthorized or invalid token")
        return

    while True:
        try:
            input_message = await websocket.recv()
            correlation_id = str(uuid.uuid4())

            apm_client.begin_transaction("websocket_request")
            # apm_client.label(user_id=user_id, correlation_id=correlation_id)

            # Capture a span for producing and consuming Kafka messages
            with capture_span("kafka_produce_consume", span_type="kafka"):
                produce(
                    input_message,
                    "request",
                    user_id=user_id,
                    correlation_id=correlation_id,
                )
                output_text = consume(
                    target_user_id=user_id, target_correlation_id=correlation_id
                )

            apm_client.end_transaction("message_processed", "success")
            await websocket.send(output_text)
        except ConnectionClosedError:
            logger.warning("WebSocket connection closed by client.")
            apm_client.capture_message("WebSocket connection closed by client.")
            break
        except Exception as e:
            logger.error(f"Error during message processing: {str(e)}")
            apm_client.capture_exception()
            await websocket.send(
                json.dumps({"error": "An error occurred during processing"})
            )
            break


async def main():
    async with websockets.serve(generate, "", 8001, ping_interval=20, ping_timeout=60):
        logger.info(f"Authentication URL :: {permission_url}")
        await asyncio.Future()


if __name__ == "__main__":
    apm_client.begin_transaction("app_start")
    try:
        asyncio.run(main())
        apm_client.end_transaction("app_start", "success")
    except Exception as e:
        logger.error(f"Error starting application: {str(e)}")
        apm_client.capture_exception()
        apm_client.end_transaction("app_start", "failure")
