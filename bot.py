from transformers import AutoModelForCausalLM, AutoTokenizer

model_name='lmsys/fastchat-t5-3b-v1.0'

# tokenizer = AutoTokenizer.from_pretrained(model_name)
# tokenizer.pad_token = tokenizer.eos_token  # Llama has no pad token by default
# model = AutoModelForCausalLM.from_pretrained(model_name, device_map="auto", load_in_4bit=True)

from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse

app = Flask(__name__)

@app.route('/bot', methods=['POST'])
def bot():
    incoming_msg = request.values.get('Body', '')
    print(incoming_msg)

    resp = MessagingResponse()
    msg = resp.message()
    msg.body(incoming_msg)
    return str(msg)