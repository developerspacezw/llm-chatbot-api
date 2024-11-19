import json
import logging
import os

import torch
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
from transformers import AutoModelForCausalLM, AutoTokenizer

load_dotenv()


# Set up a logger
logger = logging.getLogger("llm_sever_logger")
logger.setLevel(logging.DEBUG)  # Set the minimum logging level to DEBUG

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Set handler-specific level

# Create a file handler
file_handler = logging.FileHandler("llm_server.log")
file_handler.setLevel(logging.DEBUG)

# Define a log message format
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")
llm_model = os.getenv("LLM_MODEL")

logger.info("Initializing model...................")


model = AutoModelForCausalLM.from_pretrained(llm_model)
tokenizer = AutoTokenizer.from_pretrained(llm_model)
logger.info("Initializing model Complete")
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
logger.info(f"Model loaded on {device}")

producer_config = {
    "bootstrap.servers": bootstrap_server_url,
}

consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "llm_group_server",
    "auto.offset.reset": "earliest",
}

# Kafka producer and consumer configuration
schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})

# Define serializers and deserializers
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(
    schema_registry_client, schema_str=open("./schemas/avro/llm.    avsc").read()
)

key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(
    schema_registry_client, schema_str=open("./schemas/avro/llm.avsc").read()
)


def delivery_report(err, msg):
    # Called once for each produced message to indicate delivery result.
    if err is not None:
        logger.error("Message delivery failed: {}".format(err))
    else:
        logger.info("Message delivered to {} [{}]".format(msg.topic(), msg.partition()))


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
            reply_to = headers.get("reply_to")
            logger.debug(msg.value())
            value_ctx = SerializationContext(llm_topic_response, MessageField.VALUE)

            # Deserialize the Avro message
            key = key_deserializer(
                msg.key(), SerializationContext(llm_topic_response, MessageField.KEY)
            )
            value = value_deserializer(msg.value(), value_ctx)
            data = json.dumps(value)
            data_dict = json.loads(data)
            logger.debug(f"Received message: {json.dumps(value)}")
            logger.debug("Received message: {}".format(data))
            inputs = tokenizer(data_dict["request"], return_tensors="pt").to(device)
            output = model.generate(
                **inputs, max_length=100, pad_token_id=tokenizer.eos_token_id
            )
            generated_text = tokenizer.decode(output[0], skip_special_tokens=True)
            # Process and prepare the response message
            logger.info(data)
            message = {
                "uuid": data_dict["uuid"],
                "request": data_dict["request"],
                "requestType": "response",
                "response": generated_text,
            }
            producer = Producer(producer_config)

            producer.produce(
                topic=reply_to,
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
        # Ensure consumer is closed once done
        consumer.close()


if __name__ == "__main__":
    llm_request()
