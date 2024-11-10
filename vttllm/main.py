import os
import uuid
import vosk
import pyaudio
from confluent_kafka import Producer,Consumer, KafkaError
from dotenv import load_dotenv
import fastavro
import queue
import ast
import json
import threading

load_dotenv()

avroschema_directory = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(avroschema_directory, "..", "schemas/avro", "llm.avsc")
home_dir = os.path.expanduser("~")
bootstrap_server_url = os.getenv("BOOSTRAP_SERVER", default="localhost:9092")
llm_topic_request = os.getenv("LLM_TOPIC_REQUEST")
llm_topic_response = os.getenv("LLM_TOPIC_RESPONSE")

response_queue = queue.Queue()

# Load Avro schema
with open(file_path, "rb") as schema_file:
    print(schema_file)
    avro_schema = fastavro.schema.load_schema(file_path)


producer_config = {
    "bootstrap.servers": bootstrap_server_url,
}

consumer_config = {
    "bootstrap.servers": bootstrap_server_url,
    "group.id": "transcribe_group",
    'auto.offset.reset': 'earliest', 
}

consumer = Consumer(consumer_config)

producer = Producer(producer_config)

consumer.subscribe([llm_topic_response])

model_path = home_dir+'/SpeechModels/vosk-model-small-en-us-0.15'


def transcribe_audio():
    model = vosk.Model(model_path)
    recognizer = vosk.KaldiRecognizer(model, 16000)
    response = response_queue.get(timeout=5.0)
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
            data = {"uuid": str(genuuid), "request": result_dict["text"],"requestType": "request", "response": ""}
            print(result_dict["text"])
            with open('avro_binary_data.avro', 'wb') as avro_binary_data:
                fastavro.schemaless_writer(avro_binary_data, avro_schema, data)
                print("Pushing Request to LLM`")
                if response[0] == str(genuuid).encode('utf-8'):
                    producer.produce(llm_topic_request , key=str(genuuid).encode('utf-8'), value=json.dumps(data).encode('utf-8'), callback=delivery_report)
                    producer.poll(0)
        producer.flush()
      
    stream.stop_stream()
    stream.close()
    p.terminate()

def respond():
    while True:
        print("Waiting to consume and respond")
        msg = consumer.poll(1000)  # adjust the timeout as needed
        if msg is None:
            continue
        if msg.error():
            if msg.error().code() == KafkaError._PARTITION_EOF:
                continue
            else:
                print(f"Consumer error: {msg.error()}")
                break

        # Check if the received response matches the correlation ID
        response_id = response_queue.get(timeout=5.0)
        avro_binary_data = msg.value()
        if avro_binary_data["genuuid"] == response_id:
            print(avro_binary_data)
            data = fastavro.schemaless_reader(avro_binary_data, avro_schema)
            print('Received message: {}'.format(data))
            break  
        consumer.commit()

      
consume_thread = threading.Thread(target=respond)
produce_thread = threading.Thread(target=transcribe_audio)  

# Delivery report callback for producer
def delivery_report(err, msg):
    if err is not None:
        print(f'Message delivery failed: {err}')
    else:
        print(f'Message delivered to {msg.topic()} [{msg.partition()}]')
        

if __name__ == "__main__":
    produce_thread.start()
    consume_thread.start()
    
    produce_thread.join()
    consume_thread.join()
    
