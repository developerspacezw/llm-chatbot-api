from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import ChannelAccount
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# Initialize the model and tokenizer
print("Initializing meta-llama model and tokenizer...")
model_name = "meta-llama/Llama-3.2-3B"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# Move model to GPU if available
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print("Model loaded on", device)

class MyBot(ActivityHandler):
    async def on_message_activity(self, turn_context: TurnContext):
        # Encode the input text and move it to the appropriate device
        input_text = turn_context.activity.text
        input_ids = tokenizer.encode(input_text, return_tensors='pt').to(device)

        # Generate output from the model
        output = model.generate(input_ids, max_length=400, pad_token_id=tokenizer.eos_token_id)

        # Decode the generated text, skipping special tokens
        output_text = tokenizer.decode(output[0], skip_special_tokens=True)

        # Send the response back to the user
        await turn_context.send_activity(output_text)

    async def on_members_added_activity(
        self,
        members_added: ChannelAccount,
        turn_context: TurnContext
    ):
        for member_added in members_added:
            if member_added.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hi there! You can try asking me anything.")
