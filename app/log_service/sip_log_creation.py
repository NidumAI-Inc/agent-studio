import os
import pymongo
from datetime import datetime
import tiktoken  # For token counting
import re
import time  # To use sleep for 5-minute intervals
from openai import OpenAI
import asyncio  # For handling asynchronous operations
from tenacity import retry, stop_after_attempt, wait_random_exponential  # For retrying API calls
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MongoDB credentials and host information
mongo_user = os.getenv("MONGO_USER")
mongo_password = os.getenv("MONGO_PASSWORD")
mongo_host = os.getenv("MONGO_HOST")
database_name = "voice_ai_app_db"
call_logs_collection_name = "call_logs"
users_collection_name = "users"

# Build the MongoDB connection URI
mongo_uri = (
    f"mongodb+srv://{mongo_user}:{mongo_password}@{mongo_host}"
    f"{database_name}?retryWrites=true&w=majority"
)

# Connect to MongoDB
client = pymongo.MongoClient(mongo_uri)
db = client[database_name]
call_logs_collection = db[call_logs_collection_name]
users_collection = db[users_collection_name]

# Define the path to the logs directory
logs_dir = '/root/backend/Phone-Call-Agent-backend/logs'  # Use the default folder as specified

# Define costs per token (Hard-coded values)
COST_PER_TOKEN_LLM = 0.00002   # Example value
COST_PER_TOKEN_STT = 0.00001   # Example value
COST_PER_TOKEN_TTS = 0.000015  # Example value
PLATFORM_COST = 0.00005        # Example value


# Function to count tokens
def count_tokens(text, model_name='gpt-4o'):
    encoding = tiktoken.encoding_for_model(model_name)
    num_tokens = len(encoding.encode(text))
    return num_tokens

# Function to process log files
def process_log_file(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
    timestamps = []
    messages = []
    i = 0
    total_tokens_llm = 0
    total_tokens_stt = 0
    total_tokens_tts = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith('['):
            # Extract timestamp
            timestamp_match = re.match(r'\[(.*?)\]', line)
            if timestamp_match:
                timestamp_str = timestamp_match.group(1)
                try:
                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    # Skip lines with incorrect timestamp format
                    i += 1
                    continue
                # Extract speaker
                if 'AGENT:' in line:
                    speaker = 'AGENT'
                elif 'USER:' in line:
                    speaker = 'USER'
                else:
                    i += 1
                    continue
                # Extract message
                message_lines = []
                i += 1
                while i < len(lines) and not lines[i].startswith('['):
                    message_lines.append(lines[i].strip())
                    i += 1
                message = '\n'.join(message_lines)
                timestamps.append(timestamp)

                # Count tokens and assign to appropriate category
                tokens = count_tokens(message)
                if speaker == 'USER':
                    total_tokens_stt += tokens  # User messages involve speech-to-text
                elif speaker == 'AGENT':
                    total_tokens_llm += tokens  # Agent messages involve LLM
                    total_tokens_tts += tokens  # Agent messages are also converted to speech

                messages.append({
                    'timestamp': timestamp,
                    'speaker': speaker,
                    'message': message,
                    'tokens': tokens
                })
            else:
                i +=1
        else:
            i += 1

    return timestamps, messages, total_tokens_llm, total_tokens_stt, total_tokens_tts

# Function to find agent information from the users collection
def find_agent_info(agent_identifier, identifier_type):
    if identifier_type == 'phone_number':
        # Normalize phone number by removing '+' and any non-digit characters
        normalized_number = re.sub(r'\D', '', agent_identifier)
        # Build query to match phone numbers ending with the normalized number
        query = {'agents.phone_number': {'$regex': f'{normalized_number}$'}}
        projection = {'agents.$': 1, '_id': 1}
    elif identifier_type == 'agent_id':
        # For web calls, match agent_id
        query = {'agents.id': agent_identifier}
        projection = {'agents.$': 1, '_id': 1}
    else:
        return None, None

    user_doc = users_collection.find_one(query, projection)
    if user_doc and 'agents' in user_doc:
        agent_info = user_doc['agents'][0]
        user_id = str(user_doc['_id'])  # Convert ObjectId to string
        return agent_info, user_id
    else:
        return None, None


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)

# New function to analyze conversation using OpenAI with retry logic
@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(5))
async def analyze_conversation(messages):
    def _analyze():
        conversation_text = "\n".join([f"{msg['speaker']}: {msg['message']}" for msg in messages])
        
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
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": conversation_text}
                ],
                model="gpt-3.5-turbo",
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error in conversation analysis: {e}")
            return None

    return await asyncio.to_thread(_analyze)
# Main processing function
async def process_logs():
    while True:
        # Walk through the logs directory
        for dir_name in os.listdir(logs_dir):
            dir_path = os.path.join(logs_dir, dir_name)
            if os.path.isdir(dir_path):
                # Processing each log file in the directory
                for file_name in os.listdir(dir_path):
                    if file_name.endswith('.log'):
                        file_path = os.path.join(dir_path, file_name)
                        try:
                            call_log_id, agent_phone_with_ext = file_name.split('_', 1)
                            agent_phone_number = agent_phone_with_ext[:-4]  # Remove .log extension
                        except ValueError:
                            continue  # Skip files that don't match the expected format

                        # Process the log file
                        timestamps, messages, total_tokens_llm, total_tokens_stt, total_tokens_tts = process_log_file(file_path)
                        if timestamps:
                            start_time = min(timestamps)
                            end_time = max(timestamps)
                            duration = (end_time - start_time).total_seconds()

                            # Find agent info and user ID based on the phone number
                            agent_info, user_id = find_agent_info(agent_phone_number, 'phone_number')
                            if agent_info:
                                agent_id = agent_info.get('id')
                                agent_name = agent_info.get('agent_name')
                                tts_name = agent_info.get('TTS_provider')
                                stt_name = agent_info.get('stt_provider')
                                llm_name = agent_info.get('LLM_provider')
                            else:
                                agent_id = None
                                agent_name = None
                                tts_name = None
                                stt_name = None
                                llm_name = None

                            # Calculate costs
                            cost_llm = total_tokens_llm * COST_PER_TOKEN_LLM
                            cost_stt = total_tokens_stt * COST_PER_TOKEN_STT
                            cost_tts = total_tokens_tts * COST_PER_TOKEN_TTS
                            total_cost = cost_llm + cost_stt + cost_tts + PLATFORM_COST

                            # Analyze conversation
                            conversation_analysis = await analyze_conversation(messages)

                            # Prepare the call log document
                            call_log = {
                                'call_log_id': call_log_id,
                                'agent_id': agent_id,
                                'agent_name': agent_name,
                                'agent_phone_number': agent_phone_number,
                                'user_id': user_id,
                                'start_time': start_time,
                                'end_time': end_time,
                                'duration': duration,
                                'messages': messages,
                                'tts_name': tts_name,
                                'stt_name': stt_name,
                                'llm_name': llm_name,
                                'total_tokens_llm': total_tokens_llm,
                                'total_tokens_stt': total_tokens_stt,
                                'total_tokens_tts': total_tokens_tts,
                                'cost_llm': cost_llm,
                                'cost_stt': cost_stt,
                                'cost_tts': cost_tts,
                                'platform_cost': PLATFORM_COST,
                                'total_cost': total_cost,
                                'conversation_analysis': conversation_analysis
                            }

                            # Insert into MongoDB
                            call_logs_collection.insert_one(call_log)

                            # Delete the log file after processing
                            os.remove(file_path)

                # Optionally, delete the directory if empty
                if not os.listdir(dir_path):
                    os.rmdir(dir_path)

        # Wait for 5 minutes before the next iteration
        await asyncio.sleep(300)  # Sleep for 300 seconds (5 minutes)

# Run the main processing function
if __name__ == "__main__":
    asyncio.run(process_logs())
