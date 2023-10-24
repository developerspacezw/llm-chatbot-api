import asyncio
import websockets
from transformers import AutoTokenizer, AutoModelForCausalLM
# tokenizer = AutoTokenizer.from_pretrained("cerebras/Cerebras-GPT-1.3B")
# model = AutoModelForCausalLM.from_pretrained("cerebras/Cerebras-GPT-1.3B")

print("Initializaing model...................")
tokenizer = AutoTokenizer.from_pretrained("gpt2")
model = AutoModelForCausalLM.from_pretrained("gpt2")
print("Model Initialization Complete.")
print("Starting Websocket server")
async def generate(websocket):
    while True:
        input_message = await websocket.recv()
        print(input_message)
        # await websocket.send(input_message)
        input_ids = tokenizer.encode(input_message, return_tensors='pt')
        output = model.generate(input_ids, max_length=2048, pad_token_id=tokenizer.eos_token_id)
        output_text=tokenizer.decode(output[:,input_ids.shape[-1]:][0],skip_special_tokens=True)
        await websocket.send(output_text)

async def main():   
    async with websockets.serve(generate, "", 8001):
        await asyncio.Future()  
    
if __name__ == "__main__":
    asyncio.run(main())