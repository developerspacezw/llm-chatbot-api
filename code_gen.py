from transformers import pipeline

def generate_code(text):
    # Load the model for text generation from Hugging Face
    code_generator = pipeline("text2text-generation", model="gpt2")
    # code_generator = pipeline("text2code", model="gpt2")
    
    # Generate code based on the input text
    generated_code = code_generator(text, max_new_tokens=50)[0]['generated_text']

    return generated_code

if __name__ == "__main__":
    # Example text describing the OpenShift model
    input_text = "Create an OpenShift deployment called test-deployment with two replicas and expose it on port 8080."

    # Generate code based on the input text
    generated_code = generate_code(input_text)

    # Print the generated code
    print("Generated Code:")
    print(generated_code)