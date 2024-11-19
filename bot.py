import logging
import os

import torch
from flask import Flask, jsonify, request
from transformers import AutoModelForCausalLM, AutoTokenizer

# Set up a logger
logger = logging.getLogger("bot_llm_logger")
logger.setLevel(logging.DEBUG)  # Set the minimum logging level to DEBUG

# Create a console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)  # Set handler-specific level

# Create a file handler
file_handler = logging.FileHandler("bot_app.log")
file_handler.setLevel(logging.DEBUG)

# Define a log message format
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add the handlers to the logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

app = Flask(__name__)

# Initialize model and tokenizer once at startup
logger.info("Loading model and tokenizer...")
model_name = os.getenv("LLM_MODEL")
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Move model to GPU if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
logger.info("Model and tokenizer loaded successfully on", device)


@app.route("/api/messages", methods=["POST"])
def bot():
    # Get prompt from incoming JSON payload
    data = request.get_json()
    prompt = data.get("prompt", "")

    # Ensure prompt is not empty
    if not prompt:
        logger.error("error : No prompt provided")
        return jsonify({"error": "No prompt provided"}), 400

    # Tokenize and generate response, sending inputs to GPU if available
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    output = model.generate(
        **inputs, max_length=100, pad_token_id=tokenizer.eos_token_id
    )
    generated_text = tokenizer.decode(output[0], skip_special_tokens=True)

    # Create JSON response
    response = {"type": "message", "text": generated_text}
    return jsonify(response), 200


if __name__ == "__main__":
    app.run()
