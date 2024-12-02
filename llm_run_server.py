import json
import logging
import os
import threading

import PyPDF2
import torch
import weaviate
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
from flask import Flask, jsonify, request
from minio import Minio
from minio.error import S3Error
from transformers import LlamaForCausalLM, LlamaTokenizer
from werkzeug.utils import secure_filename

import authentication.jwt as auth

# Initialize MinIO Client
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_BUCKET_NAME = os.getenv("MINIO_BUCKET_NAME")

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


def generate_embeddings(text):
    """Generate embeddings for a given text using OpenLlama."""
    device_check = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device_check)
    inputs = tokenizer(
        text, return_tensors="pt", padding=True, truncation=True, max_length=512
    ).to(device_check)
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True)
    hidden_states = outputs.hidden_states[-1]
    embeddings = hidden_states.mean(dim=1)
    return embeddings.squeeze(0).cpu().numpy()


def extract_text_from_pdf(file_stream):
    """Extract text from a PDF file."""
    text = ""
    reader = PyPDF2.PdfReader(file_stream)  # Directly use the file stream
    for page in reader.pages:
        text += page.extract_text() + "\n"
    return text


def add_to_weaviate(title, content, embedding, class_name="Document"):
    """Add the text and embedding of a document to Weaviate."""
    if not client.schema.exists(class_name):
        client.schema.create_class(
            {
                "class": class_name,
                "vectorizer": "none",
                "properties": [
                    {
                        "name": "title",
                        "dataType": ["string"],
                        "description": "The title of the document",
                    },
                    {
                        "name": "content",
                        "dataType": ["string"],
                        "description": "The content of the document",
                    },
                ],
            }
        )

    logger.info(f"Embedding Document :: {title}")
    client.data_object.create(
        data_object={
            "title": title,
            "content": content,
        },
        class_name=class_name,
        vector=embedding.tolist(),
    )


@app.route("/health", methods=["GET"])
def health_check():
    if service_ready:
        return jsonify({"status": "healthy"}), 200
    else:
        return jsonify({"status": "initializing"}), 503


@app.route("/api/v1/doc/upload", methods=["POST"])
def upload_pdf():
    """Handle PDF upload, extract text, and store in Weaviate."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return jsonify({"error": "Missing or invalid Authorization header"}), 401
    token = auth_header.split("Bearer ")[1].strip()
    user_id = auth.JWT.get_user_id_from_token(token)
    if user_id == "":
        return jsonify({"error": "Invalid Authorization"}), 401
    if "file" not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400
    if file and file.filename.endswith(".pdf") or file.filename.endswith(".PDF"):
        logger.info(f"Uploading file: {file.filename}")
        filename = secure_filename(file.filename)

        try:
            # Upload file to MinIO
            minio_client.put_object(
                bucket_name=MINIO_BUCKET_NAME,
                object_name=filename,
                data=file.stream,  # Use the file's stream
                length=file.content_length,
                content_type=file.content_type,
            )
            logger.info(f"File {filename} uploaded to MinIO bucket {MINIO_BUCKET_NAME}")

            # Extract text from the file stream (not file path)
            text = extract_text_from_pdf(file.stream)

            # Generate embeddings and add to Weaviate
            embedding = generate_embeddings(text)
            add_to_weaviate(title=filename, content=text, embedding=embedding)

            return (
                jsonify(
                    {"message": f"PDF '{filename}' added to Weaviate successfully!"}
                ),
                200,
            )
        except S3Error as e:
            logger.error(f"Failed to upload file to MinIO: {e}")
            return jsonify({"error": f"Failed to upload file: {e}"}), 500
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Invalid file type, only PDF is allowed"}), 400


# Initialize Weaviate Client
WEAVIATE_URL = os.getenv(
    "WEAVIATE_URL", default=os.getenv("WEAVIATE_URL", default="http://localhost:8080")
)
client = weaviate.Client(url=WEAVIATE_URL)


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

logger.info("Initializing model...................")

# Load model and tokenizer
model = LlamaForCausalLM.from_pretrained(
    llm_model, torch_dtype=torch.float16, device_map="auto"
)
tokenizer = LlamaTokenizer.from_pretrained(llm_model)
# Set padding token if not already set
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
logger.info("Model initialization complete")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
logger.info(f"Model loaded on {device}")
logger.info(f"Connected to Vector DB : READY {client.is_ready()}")
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
            logger.debug(msg.value())
            value_ctx = SerializationContext(llm_topic_response, MessageField.VALUE)

            key = key_deserializer(
                msg.key(), SerializationContext(llm_topic_response, MessageField.KEY)
            )
            value = value_deserializer(msg.value(), value_ctx)
            data = json.dumps(value)
            data_dict = json.loads(data)
            logger.debug(f"Received message: {json.dumps(value)}")
            input_ids = tokenizer(data_dict["request"], return_tensors="pt").input_ids
            input_ids = input_ids.to(device)
            generation_output = model.generate(input_ids=input_ids, max_new_tokens=32)
            generated_text = tokenizer.decode(generation_output[0])
            logger.info(generated_text)

            message = {
                "uuid": data_dict["uuid"],
                "request": data_dict["request"],
                "requestType": "response",
                "response": str(generated_text),
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
