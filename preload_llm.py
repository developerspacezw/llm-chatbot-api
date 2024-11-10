import os
from transformers import AutoTokenizer, AutoModelForCausalLM
from dotenv import load_dotenv

load_dotenv()

llm_model = os.getenv("LLM_MODEL") 

print("Downloading model...................")
model = AutoModelForCausalLM.from_pretrained(llm_model)
tokenizer = AutoTokenizer.from_pretrained(llm_model)
print("Downloading model Complete") 