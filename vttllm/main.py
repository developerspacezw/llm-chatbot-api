import asyncio
import json
import logging
import os
import uuid

import pyaudio
import requests
import vosk
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

import authentication.jwt as auth

# Set up a logger
logger = logging.getLogger("vtl_llm_websocket_logger")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler("vtl_websocket.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Load environment variables
load_dotenv()

# Configuration
bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")
model_path = (
    "../SpeechModels/vosk-model-en-us-0.42-gigaspeech/vosk-model-en-us-0.42-gigaspeech"
)
permission_url = os.getenv("PERMISSIONS_URL")
ollama_api_url = os.getenv(
    "OLLAMA_API_URL", "http://localhost:11434/api/generate"
)  # Ollama API endpoint

# Kafka producer/consumer configuration
schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(
    schema_registry_client, schema_str=open("../schemas/avro/llm.avsc").read()
)
key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(
    schema_registry_client, schema_str=open("../schemas/avro/llm.avsc").read()
)

producer_config = {"bootstrap.servers": bootstrap_server_url}
consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "transcribe_group",
    "auto.offset.reset": "earliest",
}

producer = Producer(producer_config)
consumer = Consumer(consumer_config)


def delivery_report(err, msg):
    # Called once for each produced message to indicate delivery result.
    if err is not None:
        logger.error("Message delivery failed: {}".format(err))
    else:
        logger.info("Message delivered to {} [{}]".format(msg.topic(), msg.partition()))


# Transcribe Audio
async def transcribe_audio(user_id):
    # Initialize Vosk model and audio stream
    model = vosk.Model(model_path)
    recognizer = vosk.KaldiRecognizer(model, 16000)
    p = pyaudio.PyAudio()
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=16000,
        input=True,
        frames_per_buffer=1024,
    )

    try:
        logger.info(f"User {user_id} - Awaiting Speech-to-Text Recognition...")
        while True:
            data = stream.read(4000, exception_on_overflow=False)
            if len(data) == 0:
                break

            # Process audio and check if transcription is complete
            if recognizer.AcceptWaveform(data):
                result = recognizer.Result()
                result_dict = json.loads(result)
                transcribed_text = result_dict.get("text", "")
                logger.info(f"User {user_id} - Transcribed text: {transcribed_text}")

                # Prepare Kafka message
                message_key = str(uuid.uuid4())
                message_value = {
                    "uuid": message_key,
                    "request": transcribed_text,
                    "requestType": "request",
                    "response": "",
                }

                # Send transcription to Kafka
                try:
                    producer.produce(
                        topic=llm_topic_request,
                        key=key_serializer(
                            message_key,
                            SerializationContext(llm_topic_request, MessageField.KEY),
                        ),
                        value=value_serializer(
                            message_value,
                            SerializationContext(llm_topic_request, MessageField.VALUE),
                        ),
                        on_delivery=delivery_report,
                        headers={
                            "correlation_id": message_key,
                            "reply_to": llm_topic_response,
                            "user_id": user_id,
                        },
                    )
                    producer.flush()
                    logger.info(f"User {user_id} - Message sent to Kafka.")

                    # Await Kafka response and return it
                    response = await consume_response(message_key, user_id)
                    logger.info(f"User {user_id} - Kafka response received: {response}")
                    return response

                except KafkaException as e:
                    logger.error(f"User {user_id} - Failed to produce message: {e}")
                    return None

    except Exception as e:
        logger.error(f"Error during transcription for user {user_id}: {e}")
        return None

    finally:
        # Ensure resources are properly released
        stream.stop_stream()
        stream.close()
        p.terminate()


# Consume Kafka Response
async def consume_response(correlation_id, user_id):
    consumer.subscribe([llm_topic_response])
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Consumer error: {msg.error()}")
                continue

            headers = {
                header[0]: header[1].decode() for header in (msg.headers() or [])
            }
            logger.info(headers.get("correlation_id"))
            logger.info(headers.get("user_id"))
            if (
                headers.get("correlation_id") == correlation_id
                and headers.get("user_id") == user_id
            ):
                value = value_deserializer(
                    msg.value(),
                    SerializationContext(llm_topic_response, MessageField.VALUE),
                )
                logger.info(f"User {user_id} - Received response: {json.dumps(value)}")
                return value["response"]
        return "No matching response found"
    except KeyboardInterrupt:
        logger.warning("Consumer interrupted by user")
    finally:
        consumer.close()


# Call Ollama API for LLM response
async def call_ollama_api(prompt):
    try:
        payload = {
            "model": "deepseek-r1:8b",  # Replace with your Ollama model name
            "prompt": prompt,
            "stream": False,  # Set to True if you want streaming responses
        }
        response = requests.post(ollama_api_url, json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "No response from Ollama API")
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}")
        return None


# WebSocket Server Handler
async def generate(websocket, path):
    headers = websocket.request_headers
    bearer_token = headers.get("Authorization", "").replace("Bearer ", "")

    user_id = auth.JWT.get_user_id_from_token(bearer_token)
    if not user_id:
        await websocket.send(json.dumps({"error": "Unauthorized"}))
        logger.info("Unauthorized WebSocket connection attempt.")
        return

    logger.info(f"WebSocket client connected for user {user_id}")
    async for message in websocket:
        request = json.loads(message)
        if request.get("action") == "TRANSCRIBE":
            # Transcribe audio
            transcribed_text = await transcribe_audio(user_id)
            if not transcribed_text:
                await websocket.send(
                    json.dumps({"error": "Failed to transcribe or process audio"})
                )
                continue

            # Call Ollama API with the transcribed text
            llm_response = await call_ollama_api(transcribed_text)
            if llm_response:
                await websocket.send(
                    json.dumps({"type": "response", "text": llm_response})
                )
            else:
                await websocket.send(
                    json.dumps({"error": "Failed to get response from Ollama API"})
                )


async def main():
    async with websockets.serve(generate, "", 8765):
        await asyncio.Future()


# Start WebSocket Server
if __name__ == "__main__":
    asyncio.run(main())
    logger.info("Starting WebSocket server")
