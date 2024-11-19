import asyncio
import websockets
import os
import uuid
import vosk
import pyaudio
import requests
import authentication.jwt as auth
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka import Producer, Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import StringSerializer, StringDeserializer
from dotenv import load_dotenv
import json
import logging

# Set up a logger
logger = logging.getLogger("vtl_llm_websocket_logger")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler("vtl_websocket.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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
model_path = '../SpeechModels/vosk-model-en-us-0.42-gigaspeech/vosk-model-en-us-0.42-gigaspeech'
permission_url = os.getenv("PERMISSIONS_URL")

# Kafka producer/consumer configuration
schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(schema_registry_client, schema_str=open('../schemas/avro/llm.avsc').read())
key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(schema_registry_client, schema_str=open('../schemas/avro/llm.avsc').read())

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
        logger.error('Message delivery failed: {}'.format(err))
    else:
        logger.info('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))

# Transcribe Audio
async def transcribe_audio(websocket, user_id):
    model = vosk.Model(model_path)
    recognizer = vosk.KaldiRecognizer(model, 16000)
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)

    logger.info(f"User {user_id} - Awaiting Speech-to-Text Recognition...")
    while True:
        data = stream.read(4000)
        if len(data) == 0:
            break
        if recognizer.AcceptWaveform(data):
            result = recognizer.Result()
            result_dict = json.loads(result)
            logger.info(f"User {user_id} - Transcribed text: {result_dict['text']}")

            message_key = str(uuid.uuid4())
            message_value = {
                "uuid": message_key,
                "request": result_dict["text"],
                "requestType": "request",
                "response": ""
            }

            # Send the transcription over WebSocket
            await websocket.send(json.dumps({"type": "transcription", "text": result_dict["text"]}))

            # Send to Kafka
            try:
                producer.produce(
                    topic=llm_topic_request,
                    key=key_serializer(message_key, SerializationContext(llm_topic_request, MessageField.KEY)),
                    value=value_serializer(message_value, SerializationContext(llm_topic_request, MessageField.VALUE)),
                    on_delivery=delivery_report,
                    headers={"correlation_id": message_key, "reply_to": llm_topic_response, "user_id": user_id},
                )
                producer.flush()
                logger.info(f"User {user_id} - Message sent to Kafka. Waiting for response...")
                response = await consume_response(message_key, user_id)
                await websocket.send(json.dumps({"type": "response", "text": response}))
            except KafkaException as e:
                logger.error(f"User {user_id} - Failed to produce message: {e}")

    stream.stop_stream()
    stream.close()
    p.terminate()


# Consume Kafka Response
async def consume_response(correlation_id, user_id):
    consumer.subscribe([llm_topic_response])
    while True:
        msg = consumer.poll(timeout=1.0)
        if msg is None:
            continue
        if msg.error():
            logger.error(f"Consumer error: {msg.error()}")
            continue

        headers = {header[0]: header[1].decode() for header in (msg.headers() or [])}
        logger.info(headers.get("correlation_id"))
        logger.info(headers.get("user_id"))
        if headers.get("correlation_id") == correlation_id and headers.get("user_id") == user_id:
            key = key_deserializer(msg.key(), SerializationContext(llm_topic_response, MessageField.KEY))
            value = value_deserializer(msg.value(), SerializationContext(llm_topic_response, MessageField.VALUE))
            logger.info(f"User {user_id} - Received response: {json.dumps(value)}, Key: {key}")
            return value["response"]


# WebSocket Server Handler
async def websocket_handler(websocket, path):
    headers = websocket.request_headers
    bearer_token = headers.get("Authorization", "").replace("Bearer ", "")

    user_id = auth.JWT.get_user_id_from_token(bearer_token)
    if not user_id:
        await websocket.send(json.dumps({"error": "Unauthorized"}))
        logger.info("Unauthorized WebSocket connection attempt.")
        return

    logger.info(f"WebSocket client connected for user {user_id}")
    try:
        await transcribe_audio(websocket, user_id)
    except Exception as e:
        logger.error(f"Error for user {user_id}: {e}")
    finally:
        logger.info(f"WebSocket client disconnected for user {user_id}")


# Start WebSocket Server
if __name__ == "__main__":
    start_server = websockets.serve(websocket_handler, "", 8765)
    logger.info("Starting WebSocket server")
    asyncio.get_event_loop().run_until_complete(start_server)
    asyncio.get_event_loop().run_forever()
