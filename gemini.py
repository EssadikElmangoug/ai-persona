from ollama import chat
from ollama import ChatResponse
import os
import requests
import ollama

def get_ollama_models():
    try:
        # Get the list of models from Ollama API
        response = ollama.list()
        
        # Extract model information including name and size
        models = []
        for model in response.models:
            models.append({
                "name": model.model,
                "size": model.size,
                "modified_at": model.modified_at
            })
        
        # Sort alphabetically by name
        models.sort(key=lambda x: x["name"])
        return models
    except Exception as e:
        print(f"Error fetching models: {str(e)}")
        return []

def get_ollama_response(messages, model='llama3.2:3b'):
    # Create the base messages list with the system prompt
    print(model)
    messages_context = [
        {"role": "system", "content": ""}]
    
    # Add user messages if they exist
    if isinstance(messages, list):
        for msg in messages:
            messages_context.append(msg)
    else:
        # If it's just a string, add it as a user message
        messages_context.append({"role": "user", "content": str(messages)})

    # Generate response using the specified model
    try:
        # Using the chat API with the messages format
        response: ChatResponse = chat(model=model, messages=messages_context)
        return response.message.content
    except Exception as e:
        return f"Error: {str(e)}"