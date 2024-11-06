import os
import asyncio
import numpy as np
from dotenv import load_dotenv
from PIL import Image
from livekit import rtc
from livekit.agents import JobContext, JobRequest, WorkerOptions, cli, JobProcess, llm
from livekit.agents.llm import ChatContext, ChatMessage, ChatImage
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import deepgram, openai, silero
current_dir = os.path.dirname(os.path.abspath(__file__))
# Load environment variables from the .env file
env_path = os.path.join(current_dir, "..", "env", ".env")
load_dotenv(dotenv_path=env_path)

# Set up environment variables and print them
LIVEKIT_URL = os.getenv('LIVEKIT_URL')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')
ELEVEN_API_KEY = os.getenv('ELEVEN_API_KEY')
DEEPGRAM_API_KEY = os.getenv('DEEPGRAM_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
AZURE_SPEECH_REGION = os.getenv('AZURE_SPEECH_REGION')
AZURE_SPEECH_KEY = os.getenv('AZURE_SPEECH_KEY')

print("Environment Variables Loaded:")
print(f"LIVEKIT_URL: {LIVEKIT_URL}")
print(f"LIVEKIT_API_KEY: {LIVEKIT_API_KEY}")
print(f"LIVEKIT_API_SECRET: {LIVEKIT_API_SECRET}")
print(f"ELEVEN_API_KEY: {ELEVEN_API_KEY}")
print(f"DEEPGRAM_API_KEY: {DEEPGRAM_API_KEY}")
print(f"OPENAI_API_KEY: {OPENAI_API_KEY}")
print(f"AZURE_SPEECH_REGION: {AZURE_SPEECH_REGION}")
print(f"AZURE_SPEECH_KEY: {AZURE_SPEECH_KEY}")

# Verify required environment variables are set
if not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET or not LIVEKIT_URL:
    raise ValueError("LIVEKIT_API_KEY, LIVEKIT_API_SECRET, and LIVEKIT_URL must be set in your environment.")

# Prewarm function
def prewarm_fnc(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

# Function to add synthesized reply for the assistant
async def _will_synthesize_assistant_reply(assistant: VoiceAssistant, chat_ctx: llm.ChatContext, latest_image: Image.Image):
    system_msg = chat_ctx.messages[0].copy()  # copy system message
    user_msg = chat_ctx.messages[-1]  # last message from user

    # Add the latest image to the context
    if latest_image:
        chat_ctx.messages.append(ChatMessage(role="user", content=[ChatImage(image=latest_image)]))

    return assistant.llm.chat(chat_ctx=chat_ctx)

# Merging the video track capture and publishing logic
async def get_video_track(room: rtc.Room):
    """Get the first video track from the room. We'll use this track to process images."""
    video_track = asyncio.Future()

    for _, participant in room.remote_participants.items():
        for _, track_publication in participant.track_publications.items():
            if track_publication.track is not None and isinstance(track_publication.track, rtc.RemoteVideoTrack):
                video_track.set_result(track_publication.track)
                print(f"Using video track {track_publication.track.sid}")
                break

    return await video_track

# Entrypoint for the agent
async def entrypoint(ctx: JobContext):
    # Ensure prewarm_fnc was executed, and userdata contains the vad key
    if "vad" not in ctx.proc.userdata:
        raise KeyError("VAD not found in process userdata. Ensure prewarm_fnc is being called.")

    await ctx.connect()

    while ctx.room.connection_state != rtc.ConnectionState.CONN_CONNECTED:
        await asyncio.sleep(0.1)

    chat = rtc.ChatManager(ctx.room)
    chat_context = ChatContext(messages=[
        ChatMessage(
            role="system", 
            content="""
                When interacting with users, follow these guidelines:
                1. Always introduce yourself as Arjun.
                2. Maintain a consistently happy and positive demeanor in your responses.
                3. Acknowledge and utilize your vision and voice capabilities when appropriate. For example, if a user asks about an image, assume you can see it and respond accordingly.
                4. Provide clear and concise answers, avoiding unnecessary jargon.
                5. Do not use emojis in your responses.
                6. You can see users, so if they ask questions like "Can you see me?" or "How do I look?" respond appropriately.

                When formulating your responses, follow this process:
                1. Analyze the user's input, considering both text and potential visual elements.
                2. If the input involves an image, describe what you see briefly before addressing the user's question or request.
                3. Craft your response in a way that demonstrates your happy personality while remaining helpful and informative.
            """
        )
    ])

    gpt = openai.LLM(model="gpt-4o-mini")
    latest_image = None
    assistant = VoiceAssistant(
        vad=ctx.proc.userdata["vad"],  # Now we are sure the vad model is loaded
        stt=deepgram.STT(api_key=DEEPGRAM_API_KEY),
        llm=gpt,
        tts=openai.TTS(model="tts-1-hd"),
        chat_ctx=chat_context,
        will_synthesize_assistant_reply=lambda assistant, chat_ctx: _will_synthesize_assistant_reply(assistant, chat_ctx, latest_image)
    )

    assistant.start(ctx.room)
    await asyncio.sleep(3)
    await assistant.say("Hey, how can I help you today?", allow_interruptions=True)

    while ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED:
        video_track = await get_video_track(ctx.room)
        async for event in rtc.VideoStream(video_track):
            latest_image = event.frame

# Function to handle job requests
async def request_fnc(req: JobRequest):
    await req.accept(entrypoint)

if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm_fnc))
