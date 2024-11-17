import os
import uuid
import vosk
import pyaudio
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka import Producer, Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import StringSerializer, StringDeserializer
from dotenv import load_dotenv
import queue
import ast
import json
import threading
import logging

# Set up a logger
logger = logging.getLogger("vtl_llm_logger")
logger.setLevel(logging.DEBUG)  # Set the minimum logging level to DEBUG

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Set handler-specific level

# Create a file handler
file_handler = logging.FileHandler("vtl_app.log")
file_handler.setLevel(logging.DEBUG)

# Define a log message format
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)
load_dotenv()

home_dir = os.path.expanduser("~")
bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")

response_queue = queue.Queue()

producer_config = {
    "bootstrap.servers": bootstrap_server_url,
}

consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "transcribe_group",
    'auto.offset.reset': 'earliest', 
}

model_path ='../SpeechModels/vosk-model-small-en-us-0.15'

# Kafka producer and consumer configuration
schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})

# Define serializers and deserializers
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(schema_registry_client, schema_str=open('../schemas/avro/llm.avsc').read())

key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(schema_registry_client, schema_str=open('../schemas/avro/llm.avsc').read())

def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")

def transcribe_audio():
    model = vosk.Model(model_path)
    recognizer = vosk.KaldiRecognizer(model, 16000)
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=1024)
    
    print('Awaiting Speech To text Recognition')
    while True:
        genuuid = uuid.uuid4()
        data = stream.read(4000)
        if len(data) == 0:
            break
        if recognizer.AcceptWaveform(data):
            print('Processing Speech to Text')
            result = recognizer.Result()
            result_dict = ast.literal_eval(result)
            value = {"uuid": str(genuuid), "request": result_dict["text"],"requestType": "request", "response": ""}
            print(result_dict["text"])
            producer = Producer(producer_config)

            # Create a serialization context for the value
            value_ctx = SerializationContext(llm_topic_request, MessageField.VALUE)

            # Serialize and send message
            try:
                producer.produce(
                    topic=llm_topic_request,
                    key=key_serializer(str(genuuid), SerializationContext(llm_topic_request, MessageField.KEY)),
                    value=value_serializer(value, value_ctx),
                    on_delivery=delivery_report,
                    headers={
                        "correlation_id": "vtl",
                        "reply_to": llm_topic_response
                    }
                )
                producer.poll(1000)
            except KafkaException as e:
                print(f"Failed to produce message: {e}")
            finally:
                producer.flush()
      
    stream.stop_stream()
    stream.close()
    p.terminate()

def respond():
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
                    print(f"Consumer error: {msg.error()}")
                    break

            # Deserialize the Avro message
            headers = dict(msg.headers())
            "vtlm" == headers.get('correlation_id')
            key = key_deserializer(msg.key(), SerializationContext(llm_topic_response, MessageField.KEY))
            value = value_deserializer(msg.value(), SerializationContext(llm_topic_response, MessageField.VALUE))
            logger.info(f"Received message: {json.dumps(value)}, Deserialized Key: {key}")
            return value["response"]
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

      
consume_thread = threading.Thread(target=respond)
produce_thread = threading.Thread(target=transcribe_audio)
        

if __name__ == "__main__":
    produce_thread.start()
    consume_thread.start()
    
    produce_thread.join()
    consume_thread.join()
    
