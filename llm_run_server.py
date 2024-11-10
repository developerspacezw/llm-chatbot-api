import os
import json
from confluent_kafka import Producer,Consumer, KafkaException
from confluent_kafka.serialization import SerializationContext, MessageField
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer, AvroDeserializer
from confluent_kafka.serialization import StringSerializer, StringDeserializer
# import torch
from dotenv import load_dotenv
# from transformers import AutoTokenizer, AutoModelForCausalLM

load_dotenv()

bootstrap_server_url = os.getenv("BOOTSTRAP_SERVER", default="localhost:9092")
schema_registry_url = os.getenv("SCHEMA_REGISTRY_URL", default="http://localhost:8081")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")
llm_model = os.getenv("LLM_MODEL")

print("Initializaing model...................")


# model = AutoModelForCausalLM.from_pretrained(llm_model)
# tokenizer = AutoTokenizer.from_pretrained(llm_model)
# print("Initializaing model Complete")
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# model.to(device)
# print("Model loaded on", device)
  
producer_config = {
    "bootstrap.servers": bootstrap_server_url,
}

consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "llm_group",
    'auto.offset.reset': 'earliest', 
}

# Kafka producer and consumer configuration
schema_registry_client = SchemaRegistryClient({"url": schema_registry_url})

# Define serializers and deserializers
key_serializer = StringSerializer("utf_8")
value_serializer = AvroSerializer(schema_registry_client, schema_str=open('./schemas/avro/llm.avsc').read())

key_deserializer = StringDeserializer("utf_8")
value_deserializer = AvroDeserializer(schema_registry_client, schema_str=open('./schemas/avro/llm.avsc').read())


def delivery_report(err, msg):
    # Called once for each produced message to indicate delivery result.
    if err is not None:
        print('Message delivery failed: {}'.format(err))
    else:
        print('Message delivered to {} [{}]'.format(msg.topic(), msg.partition()))


def llmRequest():
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
                    print(f"Consumer error: {msg.error()}")
                    break

            print(msg.value())
            value_ctx = SerializationContext(llm_topic_response, MessageField.VALUE)

            # Deserialize the Avro message
            key = key_deserializer(msg.key(), SerializationContext(llm_topic_response, MessageField.KEY))
            value = value_deserializer(msg.value(), value_ctx)
            data = json.dumps(value)
            print(f"Received message: {json.dumps(value)}")
            print('Received message: {}'.format(data))

            # Process and prepare the response message
            message = {"uuid": data[0], "request": data[2], "requestType": "response", "response": "output_text"}
            producer = Producer(producer_config)

            producer.produce(
                topic=llm_topic_response,
                key=key_serializer(key, SerializationContext(llm_topic_response, MessageField.KEY)),
                value=value_serializer(message, value_ctx),
                on_delivery=delivery_report
            )
            producer.poll(1000)
            producer.flush()

    except KeyboardInterrupt:
        print("Consumer interrupted by user")

    finally:
        # Ensure consumer is closed once done
        consumer.close()


if __name__ == '__main__':
     llmRequest()