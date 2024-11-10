import os
import asyncio
import uuid
import websockets

import json
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka import Producer, Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import StringSerializer, StringDeserializer

from confluent_kafka import avro
from dotenv import load_dotenv

load_dotenv()

# Load environment variables
bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")


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


def delivery_report(err, msg):
    if err is not None:
        print(f"Message delivery failed: {err}")
    else:
        print(f"Message delivered to {msg.topic()} [{msg.partition()}]")


def produce(Incoming_request, message_type):
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
            on_delivery=delivery_report
        )
        producer.poll(1000)
    except KafkaException as e:
        print(f"Failed to produce message: {e}")
    finally:
        producer.flush()

def consume():
    """Consume a message from the Kafka topic using Avro schema"""
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
            key = key_deserializer(msg.key(), SerializationContext(llm_topic_response, MessageField.KEY))
            value = value_deserializer(msg.value(), SerializationContext(llm_topic_response, MessageField.VALUE))
            print(f"Received message: {json.dumps(value)}")
            return value["response"]
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


print("Starting WebSocket server")


async def generate(websocket):
    while True:
        input_message = await websocket.recv()
        produce(input_message, "request")
        output_text = consume()
        await websocket.send(output_text)


async def main():
    async with websockets.serve(generate, "", 8001):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())