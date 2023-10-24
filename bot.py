from flask import Flask, request, Response
import json
from twilio.twiml.messaging_response import MessagingResponse
from transformers import AutoTokenizer, AutoModelForCausalLM


app = Flask(__name__)

print("Initializaing model...................")
tokenizer = AutoTokenizer.from_pretrained("gpt2")
model = AutoModelForCausalLM.from_pretrained("gpt2") 

print("Model Initialization Complete.")
print("Starting HTTP server")
@app.route('/api/messages', methods=['POST'])
def bot():
    incoming_msg = request.values.get('Body', '')
    input_ids = tokenizer.encode(incoming_msg, return_tensors='pt')

    output = model.generate(input_ids, max_length=100, pad_token_id=tokenizer.eos_token_id)

    output_text=tokenizer.decode(output[:,input_ids.shape[-1]:][0],skip_special_tokens=True)

    resp = MessagingResponse()
    msg = resp.message()
    msg.body(incoming_msg)
    response = {
        'type': 'message',
        'text': f"{output_text}"
    }
    return Response(json.dumps(response), mimetype='application/json', status=200)

if __name__ == '__main__':
    app.run()