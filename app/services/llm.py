import os
import requests
import asyncio
from tenacity import retry, stop_after_attempt, wait_random_exponential
from dotenv import load_dotenv
load_dotenv(dotenv_path="app/env/.env")
# Read OpenAI API key from environment variable
APIKEY_openai = os.getenv("OPENAI_API_KEY")

if not APIKEY_openai:
    raise ValueError("OpenAI API key is not set in the environment variables.")

# Define cost per token for LLM (adjust according to your actual cost)
COST_PER_TOKEN_LLM = 0.00002

# OpenAI API interaction function
def openai_LLM(chat):
    """Get response from OpenAI LLM"""
    try:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": chat,
            "temperature": 0.3,
            "stream": False,
            "max_tokens": 1000
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {APIKEY_openai}"
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        return result
    except Exception as e:
        print(f"Error with OpenAI LLM: {e}")
        return None

# Conversation analysis function
@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(5))
async def analyze_conversation(messages):
    """Analyze conversation using OpenAI"""
    def _analyze():
        conversation_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
        
        system_prompt = """
        You are an AI assistant tasked with analyzing customer service conversations. 
        Please provide a brief report that includes:
        1. The main topic or purpose of the conversation
        2. The customer's primary concern or request
        3. How well the agent addressed the customer's needs
        4. Any notable positive or negative aspects of the interaction
        5. Suggestions for improvement in future interactions
        
        Keep your analysis concise and focused on the most important aspects of the conversation.
        """
        
        try:
            url = "https://api.openai.com/v1/chat/completions"
            payload = {
                "model": "gpt-4o",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conversation_text}
                ],
                "temperature": 0.3,
                "max_tokens": 300
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {APIKEY_openai}"
            }
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            analysis = result['choices'][0]['message']['content'].strip()
            return analysis
        except Exception as e:
            print(f"Error in conversation analysis: {e}")
            return None

    return await asyncio.to_thread(_analyze)
