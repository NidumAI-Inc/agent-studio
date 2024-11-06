import asyncio
from datetime import datetime
from pymongo import MongoClient, errors
from aiofile import async_open as open
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm, JobProcess
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import deepgram, openai, silero
from livekit.plugins.openai import LLM
from llama_index.core import (
    StorageContext,
    load_index_from_storage,
)
import argparse
from llama_index.core.schema import MetadataMode
import os
import uuid
import jwt
from dotenv import load_dotenv

import os

current_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the .env file dynamically
env_path = os.path.join(current_dir, "..", "env", ".env")
load_dotenv(dotenv_path=env_path)

# Access environment variables
mongo_user = os.getenv("MONGO_USER")
mongo_password = os.getenv("MONGO_PASSWORD")
mongo_host = os.getenv("MONGO_HOST")

openai_api_key = os.getenv("OPENAI_API_KEY")
livekit_url = os.getenv("LIVEKIT_URL")
livekit_api_key = os.getenv("LIVEKIT_API_KEY")
livekit_api_secret = os.getenv("LIVEKIT_API_SECRET")
deepgram_api_key = os.getenv("DEEPGRAM_API_KEY")

database_name = "voice_ai_app_db"
collection_name = "users"

# Check if all required environment variables are loaded
if not mongo_user or not mongo_password or not mongo_host:
    raise ValueError("MongoDB connection details are missing.")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY is missing.")
if not livekit_api_key or not livekit_api_secret:
    raise ValueError("LIVEKIT_API_KEY or LIVEKIT_API_SECRET is missing.")
if not deepgram_api_key:
    raise ValueError("DEEPGRAM_API_KEY is missing.")

def parse_running_job_info(running_job_info):
    parsed_data = {}
    
    # Extract the basic accept_arguments info
    accept_arguments = running_job_info.accept_arguments
    parsed_data['name'] = accept_arguments.name
    parsed_data['identity'] = accept_arguments.identity
    parsed_data['metadata'] = accept_arguments.metadata

    # Extract the job details
    job = running_job_info.job
    parsed_data['job_id'] = job.id
    
    # Extract room information
    room = job.room
    parsed_data['room_sid'] = room.sid
    parsed_data['room_name'] = room.name
    parsed_data['empty_timeout'] = room.empty_timeout
    parsed_data['creation_time'] = room.creation_time
    parsed_data['turn_password'] = room.turn_password

    # Extract enabled codecs
    enabled_codecs = []
    for codec in room.enabled_codecs:
        enabled_codecs.append(codec.mime)
    parsed_data['enabled_codecs'] = enabled_codecs

    # Extract state information
    state = job.state
    parsed_data['state_updated_at'] = state.updated_at

    # Use getattr to safely access dispatch_id, default to None if it doesn't exist
    parsed_data['dispatch_id'] = getattr(running_job_info, 'dispatch_id', None)
    
    # Use getattr to safely access other optional attributes like url and token
    parsed_data['url'] = getattr(running_job_info, 'url', None)
    parsed_data['token'] = getattr(running_job_info, 'token', None)
    # token = getattr(running_job_info, 'token', None)
    return parsed_data

def decode_jwt_and_get_room(token):
    # Decode the payload without verifying the signature
    payload = jwt.decode(token, options={"verify_signature": False})
    # Extract the room from the payload
    room = payload.get('video', {}).get('room', None)
    if room and '_id_' in room:
        return room.split('_id_')[0]
    return room



def get_mongo_client():
    connection_string = f"mongodb+srv://{mongo_user}:{mongo_password}@{mongo_host}?retryWrites=true&w=majority"
    return MongoClient(connection_string)

# Function to retrieve assistant data from MongoDB by phone number
def get_assistant_data(phone_number):
    client = get_mongo_client()
    db = client[database_name]
    collection = db[collection_name]
    
    # Normalize the phone number by stripping any '+' prefix
    normalized_phone_number = phone_number.lstrip('+')
    
    # Create both versions of the phone number (with and without '+')
    phone_numbers_to_check = [normalized_phone_number, f'+{normalized_phone_number}']
    
    # Use the $in operator to check for both versions in the query
    user_data = collection.find_one({
        "agents.phone_number": {"$in": phone_numbers_to_check}
    })

    if user_data:
        for agent in user_data['agents']:
            # Normalize the agent's phone number as well
            agent_phone_number = agent['phone_number'].lstrip('+')
            if agent_phone_number == normalized_phone_number:
                # Extract user_id and agent_id for persist directory
                user_id = user_data['_id']
                agent_id = agent['id']
                rag_enabled = agent.get('rag_enabled', False)
                
                # If RAG is enabled, use RAG-specific assistant data
                if rag_enabled:
                    return get_rag_assistant_data(agent, user_id, agent_id)
                else:
                    return agent, None  # No persist directory needed without RAG
        print(f"No agent found with phone number: {phone_number}")
        return None, None
    else:
        print(f"No user found with an agent having phone number: {phone_number}")
        return None, None

# RAG-specific assistant data retrieval
def get_rag_assistant_data(agent, user_id, agent_id):
    print("RAG is enabled. Fetching RAG-specific assistant data...")
    
    # Define persist directory based on user_id and agent_id
    persist_dir = f"uploads/{user_id}/{agent_id}/lamadir"
    
    # Ensure the directory exists or contains necessary files
    if not os.path.exists(persist_dir):
        print(f"Persist directory not found: {persist_dir}")
    
    return agent, persist_dir

def create_identity_folder(identity):
    folder_name = f"logs/{identity}"
    os.makedirs(folder_name, exist_ok=True)
    return folder_name

def prewarm_fnc(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

# RAG-specific assistant reply synthesis
async def _will_synthesize_assistant_reply(assistant: VoiceAssistant, chat_ctx: llm.ChatContext, persist_dir):
    storage_context = StorageContext.from_defaults(persist_dir=persist_dir)
    index = load_index_from_storage(storage_context)
    system_msg = chat_ctx.messages[0].copy()  # copy system message
    user_msg = chat_ctx.messages[-1]  # last message from user

    retriever = index.as_retriever()
    nodes = await retriever.aretrieve(user_msg.content)

    system_msg.content = "Context that might help answer the user's question:"
    for node in nodes:
        node_content = node.get_content(metadata_mode=MetadataMode.LLM)
        system_msg.content += f"\n\n{node_content}"
    
    chat_ctx.messages[0] = system_msg
    return assistant.llm.chat(chat_ctx=chat_ctx)

async def entrypoint(ctx: JobContext):
    room = ctx.room
    room_items = ctx.__dict__.items()
    for key, value in room_items:
        if key == "_info":
            web_identity = decode_jwt_and_get_room(parse_running_job_info(value)["token"])
            break
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    phone_number = None
    caller_id = None
    for rp in room.remote_participants.values():
        caller_id = rp.identity
        create_identity_folder(str(caller_id))        
        try:
            phone_number = rp.attributes['sip.trunkPhoneNumber']
            print(f"Phone number: {phone_number}")
            break
        except KeyError:
            print("Phone number not found in attributes, so using web app identity: " + web_identity)
            phone_number = web_identity

    # Get assistant data based on phone number
    assistant_data, persist_dir = get_assistant_data(phone_number)
    print(assistant_data)
    if not assistant_data:
        return  # Terminate the process if no assistant data is found

    try:
        # Mapping the relevant fields from assistant_data
        system_prompt = assistant_data['system_prompt']
        first_message = assistant_data['first_message']
        language = assistant_data['language']
        voice = assistant_data['voice']
        max_tokens = assistant_data['max_tokens']
        llm_provider = assistant_data.get('LLM_provider', 'openai')  # Default to 'openai'
        llm_model = assistant_data.get('LLM_model', 'gpt-4')  # Default to 'gpt-4'
        temperature = assistant_data.get('temperature', 0.7)
        stt_provider = assistant_data.get('stt_provider', 'deepgram')  # Default STT provider
        stt_model = assistant_data.get('stt_model', 'nova-phonecall')  # Default STT model
        tts_provider = assistant_data.get('TTS_provider', 'openai')  # Default TTS provider
        tts_speed = assistant_data.get('tts_speed', 1.10)
        interrupt_speech_duration = assistant_data.get('interrupt_speech_duration', 0.35)
    except KeyError as e:
        print(f"Missing required assistant configuration field: {e}")
        return

    # Initialize the chat context with the system prompt
    initial_ctx = llm.ChatContext().append(
        role="system",
        text=system_prompt
    )

    # Handle the LLM provider selection
    if llm_provider == "server":
        print("Custom LLM is selected. Please contact info@swarmchain.org for access to this feature.")
        return
    elif llm_provider == "groq":
        llm_instance = LLM.with_groq(model=llm_model, api_key=os.getenv("GROQ_API_KEY"))
    else:
        # Default to OpenAI if no LLM provider is specified or it's 'openai'
        llm_instance = LLM(
            model=llm_model,
            api_key=openai_api_key,
            temperature=temperature
        )

    # Handle the STT provider selection
    if stt_provider == "server":
        print("Custom STT is selected. Please contact info@swarmchain.org for access to this feature.")
        return
    else:
        stt_instance = deepgram.STT(model=stt_model, language=language)

    # Handle the TTS provider selection
    if tts_provider == "server":
        print("Custom TTS is selected. Please contact info@swarmchain.org for access to this feature.")
        return
    else:
        tts_instance = openai.TTS(model="tts-1-hd", voice=voice, speed=tts_speed)

    # Initialize the VoiceAssistant
    assistant = VoiceAssistant(
        interrupt_speech_duration=interrupt_speech_duration,
        vad=ctx.proc.userdata["vad"],
        stt=stt_instance,  # Use the dynamically selected STT instance
        llm=llm_instance,  # Use the dynamically selected LLM instance
        tts=tts_instance,  # Use the dynamically selected TTS instance
        chat_ctx=initial_ctx,
        will_synthesize_assistant_reply=None if not persist_dir else
        lambda assistant, chat_ctx: _will_synthesize_assistant_reply(assistant, chat_ctx, persist_dir=persist_dir)
    )

    assistant.start(ctx.room)

    chat = rtc.ChatManager(ctx.room)

    async def answer_from_text(txt: str):
        chat_ctx = assistant.chat_ctx.copy()
        chat_ctx.append(role="user", text=txt)
        stream = assistant.llm.chat(chat_ctx=chat_ctx)
        await assistant.say(stream)

    @chat.on("message_received")
    def on_chat_received(msg: rtc.ChatMessage):
        if msg.message:
            asyncio.create_task(answer_from_text(msg.message))

    log_queue = asyncio.Queue()

    @assistant.on("user_speech_committed")
    def on_user_speech_committed(msg: llm.ChatMessage):
        if isinstance(msg.content, list):
            msg.content = "\n".join(
                "[image]" if isinstance(x, llm.ChatImage) else x for x in msg.content
            )
        log_queue.put_nowait(f"[{datetime.now()}] USER:\n{msg.content}\n\n")

    @assistant.on("agent_speech_committed")
    def on_agent_speech_committed(msg: llm.ChatMessage):
        log_queue.put_nowait(f"[{datetime.now()}] AGENT:\n{msg.content}\n\n")

    async def write_transcription(caller_id, phone_number):
        generated_uuid = str(uuid.uuid4()) + "_" + str(phone_number)
        file_name = f"logs/{caller_id}/{generated_uuid}.log"
        async with open(file_name, "w") as f:
            while True:
                msg = await log_queue.get()
                if msg is None:
                    break
                await f.write(msg)

    write_task = asyncio.create_task(write_transcription(caller_id, phone_number))

    async def finish_queue():
        log_queue.put_nowait(None)
        await write_task

    ctx.add_shutdown_callback(finish_queue)

    await assistant.say(first_message, allow_interruptions=True)

def main():
    parser = argparse.ArgumentParser(description='Agent for AI Studio')
    parser.add_argument('command', choices=['start'], help='Command to execute')
    args = parser.parse_args()

    if args.command == 'start':
        # Start the agent
        cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm_fnc))
    else:
        parser.print_help()

if __name__ == "__main__":
    main()