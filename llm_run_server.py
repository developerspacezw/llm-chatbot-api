import asyncio
import json
import logging
import os
import threading

import chromadb
import requests
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
from flask import Flask, jsonify, request
from langchain.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from minio import Minio
from werkzeug.utils import secure_filename

# Set up Elastic APM client
apm_client = Client(
    service_name="llm-server",
    server_url=os.getenv("ELASTIC_APM_SERVER_URL", "http://localhost:8200"),
    environment=os.getenv("ENVIRONMENT", "development"),
    secret_token=os.getenv("ELASTIC_APM_SECRET_TOKEN", ""),
)

# Enable auto instrumentation
apm_client.begin_transaction("custom")
apm_client.end_transaction("initialize", "success")

# Initialize MinIO Client
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME")
CHROMADB_URL = os.getenv("CHROMADB_URL")
ollama_api_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")

# Set up a logger
logger = logging.getLogger("llm_sever_logger")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

file_handler = logging.FileHandler("llm_server.log")
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")
llm_model = os.getenv("LLM_MODEL")


# Indicate that the service is ready
service_ready = True

producer_config = {"bootstrap.servers": bootstrap_server_url}
consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "llm_group_server",
    "auto.offset.reset": "earliest",
}

schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(
    schema_registry_client, schema_str=open("./schemas/avro/llm.avsc").read()
)
key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(
    schema_registry_client, schema_str=open("./schemas/avro/llm.avsc").read()
)

CHROMADB_HOST = CHROMADB_URL
chroma_client = chromadb.HttpClient(host="localhost", port=8000)

# Create or get collection
collection_name = "documents"
collection = chroma_client.get_or_create_collection(name=collection_name)

if not MINIO_ENDPOINT or not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    raise ValueError("Missing MinIO configuration. Check your environment variables.")

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False,
)

# Create bucket if it doesn't exist
if not minio_client.bucket_exists(MINIO_BUCKET_NAME):
    minio_client.make_bucket(MINIO_BUCKET_NAME)

load_dotenv()

# Flask app for health check
app = Flask(__name__)
service_ready = False  # Health check flag
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# Helper function to process PDF
def process_pdf(file_path):
    # Load and split PDF
    loader = PyPDFLoader(file_path)
    documents = loader.load()
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    docs = text_splitter.split_documents(documents)

    for i, doc in enumerate(docs):
        collection.add(
            documents=[doc.page_content],
            metadatas=[{"page_number": i + 1}],
            ids=[f"{os.path.basename(file_path)}-page-{i + 1}"],
        )
    return len(docs)


# Helper function to upload to MinIO
def upload_to_minio(file_path, bucket_name, object_name):
    with open(file_path, "rb") as file_data:
        minio_client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=file_data,
            length=os.path.getsize(file_path),
            content_type="application/pdf",
        )


# Route to upload PDF
@app.route("/api/v1/doc/upload", methods=["POST"])
def upload_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    if file and file.filename.endswith(".pdf"):
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)

        # Process the PDF
        num_chunks = process_pdf(file_path)

        # Upload to MinIO
        try:
            upload_to_minio(file_path, MINIO_BUCKET_NAME, filename)
        except Exception as e:
            return jsonify({"error": f"Failed to upload to MinIO: {str(e)}"}), 500

        return jsonify({"message": f"File uploaded, {num_chunks} chunks processed."})

    return jsonify({"error": "Invalid file type, only PDFs are allowed."}), 400


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "healthy"}), 200


# Replace vllm chat_with_model with transformers
async def chat_with_model(req):
    try:
        payload = {
            "model": llm_model,  # Replace with your Ollama model name
            "prompt": req,
            "stream": False,  # Set to True if you want streaming responses
        }
        response = requests.post(ollama_api_url, json=payload)
        response.raise_for_status()
        result = response.json()
        return result.get("response", "No response from Ollama API")
    except Exception as e:
        logger.error(f"Error calling Ollama API: {e}")
        return None


def delivery_report(err, msg):
    if err is not None:
        logger.error(f"Message delivery failed: {err}")
    else:
        logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")


def llm_request():
    consumer = Consumer(consumer_config)
    consumer.subscribe([llm_topic_request])
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

            headers = dict(msg.headers())
            correlation_id = headers.get("correlation_id")
            user_id = headers.get("user_id")
            apm_client.begin_transaction("llm_request")
            logger.debug(msg.value())
            value_ctx = SerializationContext(llm_topic_response, MessageField.VALUE)

            key = key_deserializer(
                msg.key(), SerializationContext(llm_topic_response, MessageField.KEY)
            )
            value = value_deserializer(msg.value(), value_ctx)
            data = json.dumps(value)
            data_dict = json.loads(data)
            logger.debug(f"Received message: {json.dumps(value)}")

            # Run the chat_with_model coroutine and await its result
            response = asyncio.run(chat_with_model(data_dict["request"]))

            message = {
                "uuid": data_dict["uuid"],
                "request": data_dict["request"],
                "requestType": "response",
                "response": str(response),
            }
            producer = Producer(producer_config)

            producer.produce(
                topic=str(llm_topic_response),
                key=key_serializer(
                    key, SerializationContext(llm_topic_response, MessageField.KEY)
                ),
                value=value_serializer(message, value_ctx),
                on_delivery=delivery_report,
                headers={"correlation_id": correlation_id, "user_id": user_id},
            )
            producer.poll(1000)
            producer.flush()
            apm_client.end_transaction("message_processed", "success")

    except KeyboardInterrupt:
        logger.error("Consumer interrupted by user")
    finally:
        consumer.close()


if __name__ == "__main__":
    # Start health check server in a separate thread
    threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=8123, debug=False)
    ).start()

    # Start the Kafka consumer
    llm_request()
