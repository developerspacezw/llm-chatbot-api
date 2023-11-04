# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from botbuilder.core import ActivityHandler, TurnContext
from botbuilder.schema import ChannelAccount
from transformers import AutoTokenizer, AutoModelForCausalLM

print("Initializaing model...................")
tokenizer = AutoTokenizer.from_pretrained("gpt2")
model = AutoModelForCausalLM.from_pretrained("gpt2")

class MyBot(ActivityHandler):
    # See https://aka.ms/about-bot-activity-message to learn more about the message and other activity types.

    async def on_message_activity(self, turn_context: TurnContext):
        input_ids = tokenizer.encode(turn_context.activity.text, return_tensors='pt')

        output = model.generate(input_ids, max_length=512, pad_token_id=tokenizer.eos_token_id)

        output_text=tokenizer.decode(output[:,input_ids.shape[-1]:][0],skip_special_tokens=True)

        await turn_context.send_activity(f"{ output_text }")

    async def on_members_added_activity(
        self,
        members_added: ChannelAccount,
        turn_context: TurnContext
    ):
        for member_added in members_added:
            if member_added.id != turn_context.activity.recipient.id:
                await turn_context.send_activity("Hi there you can try asking me anything")
