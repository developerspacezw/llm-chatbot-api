from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

app = Flask(__name__)

# Initialize model and tokenizer once at startup
print("Loading model and tokenizer...")
model_name = "meta-llama/Llama-3.2-3B"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Move model to GPU if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print("Model and tokenizer loaded successfully on", device)

@app.route('/api/messages', methods=['POST'])
def bot():
    # Get prompt from incoming JSON payload
    data = request.get_json()
    prompt = data.get("prompt", "")

    # Ensure prompt is not empty
    if not prompt:
        return jsonify({"error": "No prompt provided"}), 400

    # Tokenize and generate response, sending inputs to GPU if available
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    output = model.generate(**inputs, max_length=100, pad_token_id=tokenizer.eos_token_id)
    generated_text = tokenizer.decode(output[0], skip_special_tokens=True)

    # Create JSON response
    response = {
        'type': 'message',
        'text': generated_text
    }
    return jsonify(response), 200

if __name__ == '__main__':
    app.run()
