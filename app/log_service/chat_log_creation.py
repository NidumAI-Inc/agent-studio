import os
import asyncio
import threading
from datetime import datetime
from pymongo import MongoClient
from app.services.llm import analyze_conversation
from app.db.databases import get_database
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# MongoDB setup
db = get_database()
chat_logs_collection = db["chat_logs"]

async def process_chat_logs():
    while True:
        try:
            # Fetch chat logs that haven't been analyzed yet
            unprocessed_logs = chat_logs_collection.find({
                "conversation_analysis": {"$exists": False}
            })

            tasks = []

            for log in unprocessed_logs:
                chat_id = log['chat_id']
                chat_data = log['chat_data']

                # Start a new asyncio task for each conversation analysis
                task = asyncio.create_task(analyze_and_update_log(chat_id, chat_data))
                tasks.append(task)

            # Wait for all tasks to complete
            await asyncio.gather(*tasks)

            # Sleep for 5 minutes
            await asyncio.sleep(300)
        except Exception as e:
            print(f"Error processing chat logs: {e}")
            await asyncio.sleep(300)

async def analyze_and_update_log(chat_id, chat_data):
    try:
        analysis = await analyze_conversation(chat_data)

        # Update the chat log with the analysis
        chat_logs_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"conversation_analysis": analysis}}
        )
        print(f"Updated chat log {chat_id} with conversation analysis.")
    except Exception as e:
        print(f"Error analyzing chat log {chat_id}: {e}")

if __name__ == "__main__":
    asyncio.run(process_chat_logs())
