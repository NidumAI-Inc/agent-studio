from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query, BackgroundTasks, Body,Request
from livekit import api
from typing import List, Optional
from app.models.model import User, AI_Agent,CallLog,Message,DashboardData
from app.models.schemas import (
    UserCreate,
    UserUpdate,
    AgentCreate,
    AgentUpdate,
    KnowledgeBaseResponse,
    FileListResponse,
    ChatRequest,
    ChatMessage,
    DynamicDataRequest,
    CampaignUpdate,
    CampaignCreate,
    Campaign,
    PhoneNumberDeleteRequest,
    PhoneNumberUpdateRequest
)
import io
import csv


from app.db.databases import get_database
from app.services.utils import extract_text_from_file, delete_directory
from app.services.llama_index_integration import process_files_with_llama_index, load_index_and_query
import os
import uuid
import asyncio
from pydantic import BaseModel, Field, constr
import subprocess
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
from app.services.llm import openai_LLM
import csv
from fastapi.responses import FileResponse
import tempfile
import shutil
from app.services.campaign_helper import process_campaign_calls_sync
import pymongo
load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Dependency to get the database
def get_db():
    db = get_database()
    try:
        yield db
    finally:
        db.client.close()
api_key = os.getenv("LIVEKIT_API_KEY")
api_secret = os.getenv("LIVEKIT_API_SECRET")
# Directory to save CSV files
CSV_DIR = "./csv_files"
os.makedirs(CSV_DIR, exist_ok=True)
# ------------------- User Endpoints -------------------

@app.post("/users/", response_model=User)
def create_user(user: UserCreate, db=Depends(get_db)):
    if db.users.find_one({"email": user.email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user_dict = user.dict()
    user_dict["_id"] = str(uuid.uuid4())
    user_dict["agents"] = []
    db.users.insert_one(user_dict)
    return User(**user_dict)

@app.get("/users/", response_model=List[User])
def get_all_users(db=Depends(get_db)):
    users = list(db.users.find())
    return [User(**user) for user in users]

@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: str, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if user:
        return User(**user)
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.put("/users/{user_id}", response_model=User)
def update_user(user_id: str, user_update: UserUpdate, db=Depends(get_db)):
    db.users.update_one({"_id": user_id}, {"$set": user_update.dict(exclude_unset=True)})
    user = db.users.find_one({"_id": user_id})
    if user:
        return User(**user)
    else:
        raise HTTPException(status_code=404, detail="User not found")

@app.delete("/users/{user_id}")
def delete_user(user_id: str, db=Depends(get_db)):
    result = db.users.delete_one({"_id": user_id})
    if result.deleted_count:
        user_dir = f"uploads/{user_id}"
        if os.path.exists(user_dir):
            delete_directory(user_dir)
        return {"detail": "User deleted"}
    else:
        raise HTTPException(status_code=404, detail="User not found")

# ------------------- Agent Endpoints -------------------

@app.post("/users/{user_id}/agents/", response_model=AI_Agent)
def create_agent(user_id: str, agent: AgentCreate, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if any(a["phone_number"] == agent.phone_number for a in user.get("agents", [])):
        raise HTTPException(status_code=400, detail="Phone number already exists for this user")

    # Build the agent data with user-provided and default values
    agent_dict = {
        "id": str(uuid.uuid4()),
        "agent_name": agent.agent_name or "Ava",
        "phone_number": agent.phone_number,
        "LLM_provider": agent.LLM_provider or "openai",
        "LLM_model": agent.LLM_model or "GPT 3.5 Turbo Cluster",
        "stt_provider": agent.stt_provider or "google",
        "stt_model": agent.stt_model or "whisper",
        "temperature": agent.temperature or 0.7,
        "max_tokens": agent.max_tokens or 250,
        "first_message": agent.first_message or "Hello, this is Ava. How may I assist you today?",
        "system_prompt": agent.system_prompt or """Ava is a sophisticated AI training assistant...""",
        "language": agent.language or "English",
        "TTS_provider": agent.TTS_provider or "aws_polly",
        "voice": agent.voice or "nova",
        "rag_enabled": agent.rag_enabled if agent.rag_enabled is not None else True,
        "background_noise": agent.background_noise or None,
        "agent_type": agent.agent_type or "web",
        "tts_speed": agent.tts_speed or 1.0,  # Ensure default value
        "interrupt_speech_duration": agent.interrupt_speech_duration or 0.0,  # Ensure default value
        "knowledge_base": {"files": []}
    }

    db.users.update_one({"_id": user_id}, {"$push": {"agents": agent_dict}})
    return AI_Agent(**agent_dict)


@app.get("/users/{user_id}/agents/", response_model=List[AI_Agent])
def get_all_agents(user_id: str, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if user:
        agents = user.get("agents", [])
        return [AI_Agent(**agent) for agent in agents]
    else:
        return []

@app.get("/users/{user_id}/agents/{agent_id}", response_model=AI_Agent)
def get_agent(user_id: str, agent_id: str, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if user:
        agent = next((a for a in user.get("agents", []) if a["id"] == agent_id), None)
        if agent:
            # Provide default values if tts_speed or interrupt_speech_duration is missing
            agent.setdefault('tts_speed', 1.0)
            agent.setdefault('interrupt_speech_duration', 0.0)
            return AI_Agent(**agent)
    raise HTTPException(status_code=404, detail="Agent not found")


@app.put("/users/{user_id}/agents/{agent_id}", response_model=AI_Agent)
def update_agent(user_id: str, agent_id: str, agent_update: AgentUpdate, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agents = user.get("agents", [])
    for idx, agent in enumerate(agents):
        if agent["id"] == agent_id:
            updated_fields = agent_update.dict(exclude_unset=True)

            # If tts_speed and interrupt_speech_duration are not in the update, retain the original or default values
            if 'tts_speed' not in updated_fields:
                updated_fields['tts_speed'] = agent.get('tts_speed', 1.0)  # Default to 1.0 if missing
            if 'interrupt_speech_duration' not in updated_fields:
                updated_fields['interrupt_speech_duration'] = agent.get('interrupt_speech_duration', 0.0)  # Default to 0.0 if missing

            # Update the agent with the new fields
            agents[idx].update(updated_fields)

            db.users.update_one({"_id": user_id}, {"$set": {"agents": agents}})
            return AI_Agent(**agents[idx])

    raise HTTPException(status_code=404, detail="Agent not found")

@app.delete("/users/{user_id}/agents/{agent_id}")
def delete_agent(user_id: str, agent_id: str, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if user:
        agents = user.get("agents", [])
        agents = [a for a in agents if a["id"] != agent_id]
        db.users.update_one({"_id": user_id}, {"$set": {"agents": agents}})
        agent_dir = f"uploads/{user_id}/{agent_id}"
        if os.path.exists(agent_dir):
            delete_directory(agent_dir)
        return {"detail": "Agent deleted"}
    raise HTTPException(status_code=404, detail="Agent not found")

# ------------------- File Upload and Management -------------------

@app.post("/users/{user_id}/agents/{agent_id}/upload/")
async def upload_files(
    user_id: str,
    agent_id: str,
    files: List[UploadFile] = File(...),
    db=Depends(get_db)
):
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agents = user.get("agents", [])
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    lamma_dir = "lamadir"
    agent_dir = f"uploads/{user_id}/{agent_id}/{lamma_dir}"
    file_dir = f"uploads/{user_id}/{agent_id}"

    # Create directories if they don't exist
    if os.path.exists(agent_dir):
        delete_directory(agent_dir)
    os.makedirs(agent_dir, exist_ok=True)
    os.makedirs(file_dir, exist_ok=True)

    files_dir = os.path.join(file_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    # Save the uploaded files to files_dir
    for file in files:
        file_path = os.path.join(files_dir, file.filename)
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

    # Initialize variables for file processing
    combined_text = ""
    filenames = []

    # Read and process all files inside files_dir
    for filename in os.listdir(files_dir):
        file_path = os.path.join(files_dir, filename)
        with open(file_path, "rb") as f:
            content = f.read()
            text = extract_text_from_file(filename, content)
            if not text:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {filename}")
            combined_text += text + "\n"
            filenames.append(filename)

    # Save the combined text to raw_data.txt in agent_dir
    raw_data_file = os.path.join(agent_dir, "raw_data.txt")
    with open(raw_data_file, "w") as f:
        f.write(combined_text)

    # Process the files using the updated LlamaIndex logic
    process_files_with_llama_index(files_dir, agent_dir)

    # Update the agent's knowledge base with the processed filenames
    agent["knowledge_base"] = {"files": filenames}
    db.users.update_one({"_id": user_id}, {"$set": {"agents": agents}})

    return {"detail": "Files uploaded and processed successfully"}

@app.get("/users/{user_id}/agents/{agent_id}/files/", response_model=FileListResponse)
def get_uploaded_files(user_id: str, agent_id: str, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    agent = next((a for a in user.get("agents", []) if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    knowledge_base = agent.get("knowledge_base", {})
    files = knowledge_base.get("files", [])
    return FileListResponse(files=files)

@app.delete("/users/{user_id}/agents/{agent_id}/files/")
async def delete_file(
    user_id: str,
    agent_id: str,
    filename: str = Query(..., description="Name of the file to delete"),
    db=Depends(get_db)
):
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agents = user.get("agents", [])
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    lamma_dir = "lamadir"
    agent_dir = f"uploads/{user_id}/{agent_id}/{lamma_dir}"
    file_dir = f"uploads/{user_id}/{agent_id}"
    files_dir = os.path.join(file_dir, "files")
    file_path = os.path.join(files_dir, filename)

    # Check if the file exists before attempting to delete it
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    # Delete the specified file
    os.remove(file_path)
    print(f"Deleted file: {file_path}")

    # Remove the filename from the agent's knowledge_base
    agent["knowledge_base"]["files"].remove(filename)
    db.users.update_one({"_id": user_id}, {"$set": {"agents": agents}})

    # If `lamma_dir` exists, delete it to clean up old data
    if os.path.exists(agent_dir):
        delete_directory(agent_dir)
        print(f"Deleted directory: {agent_dir}")

    # Retry creating a fresh `lamma_dir` after deletion
    os.makedirs(agent_dir, exist_ok=True)
    print(f"Re-created directory: {agent_dir}")

    # Re-create embeddings with the remaining files in `files_dir`
    combined_text = ""
    remaining_files = os.listdir(files_dir)

    # If there are no remaining files, return a message indicating empty state
    if not remaining_files:
        return {"detail": f"File '{filename}' deleted. No more files to process."}

    # Process each remaining file to extract text and create embeddings
    for remaining_file in remaining_files:
        remaining_file_path = os.path.join(files_dir, remaining_file)
        with open(remaining_file_path, "rb") as f:
            content = f.read()
            text = extract_text_from_file(remaining_file, content)
            if not text:
                raise HTTPException(status_code=400, detail=f"Unsupported file type: {remaining_file}")
            combined_text += text + "\n"

    # Save the combined text from remaining files to `raw_data.txt` in `agent_dir`
    raw_data_file = os.path.join(agent_dir, "raw_data.txt")
    with open(raw_data_file, "w") as f:
        f.write(combined_text)

    # Process the remaining files using the updated LlamaIndex logic
    process_files_with_llama_index(files_dir, agent_dir)

    return {"detail": f"File '{filename}' deleted, remaining files reprocessed, and embeddings updated."}

# ------------------- Knowledge Base Info -------------------

@app.get("/users/{user_id}/agents/{agent_id}/knowledge_base/", response_model=KnowledgeBaseResponse)
def get_knowledge_base_info(user_id: str, agent_id: str, db=Depends(get_db)):
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    agent = next((a for a in user.get("agents", []) if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_dir = f"uploads/{user_id}/{agent_id}"
    raw_data_file = os.path.join(agent_dir, "raw_data.txt")
    pkl_file = os.path.join(agent_dir, "my_data.pkl")
    vdb_data_file = os.path.join(agent_dir, "vdb_data")

    knowledge_base_info = KnowledgeBaseResponse(
        files=agent["knowledge_base"].get("files", []),
        raw_data_file=raw_data_file if os.path.exists(raw_data_file) else None,
        pkl_file=pkl_file if os.path.exists(pkl_file) else None,
        vdb_data_file=vdb_data_file if os.path.exists(vdb_data_file) else None,
    )

    return knowledge_base_info
# ------------------- Retrieval API -------------------

@app.get("/users/{user_id}/agents/{agent_id}/retrieve/")
async def retrieve_documents(
    user_id: str,
    agent_id: str,
    query: str = Query(..., description="The query to retrieve documents."),
    retrieval_len: int = Query(5, description="The number of documents to retrieve."),
    db=Depends(get_db)
):
    """
    API to retrieve documents based on a query and retrieval length.
    Handles concurrent requests.
    """
    user = db.users.find_one({"_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    agent = next((a for a in user.get("agents", []) if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    lamma_dir = "lamadir"
    agent_dir = f"uploads/{user_id}/{agent_id}/{lamma_dir}"
    if not os.path.exists(agent_dir):
        raise HTTPException(status_code=404, detail="Knowledge base not found for the agent.")

    # Load the index and perform the query
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, load_index_and_query, agent_dir, query, retrieval_len)
        return {"query": query, "results": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during retrieval: {e}")

class SIPRequest(BaseModel):
    phone_number: str = Field(..., pattern=r'^\+?\d+$')  # Phone number validation
    provider: str = Field(..., pattern=r'^(twilio|telnyx)$')  # Provider validation
    email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')  # Email validation
    api_key: str
    api_secret: str
    label: str
    mapped_agent_name: str
    auth_username: str  # For outbound trunk authentication
    auth_password: str  # For outbound trunk authentication
    sip_address: Optional[str] = "sip.telnyx.com"  # Default SIP address, can be customized

# Helper function to run shell commands asynchronously
async def run_command(command: str) -> str:
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()

    if process.returncode != 0:
        raise Exception(f"Command failed with error: {stderr.decode()}")

    return stdout.decode()

# Helper function to store request logs into MongoDB
async def log_request_to_db(db, request: SIPRequest, inbound_trunk_id: str, dispatch_rule_id: str, outbound_trunk_id: str):
    try:
        db.logs.insert_one({
            "email": request.email,
            "phone_number": request.phone_number,
            "provider": request.provider,
            "inbound_trunk_id": inbound_trunk_id,
            "outbound_trunk_id": outbound_trunk_id,
            "dispatch_rule_id": dispatch_rule_id,
            "api_key": request.api_key,
            "api_secret": request.api_secret,
            "label": request.label,
            "mapped_agent_name": request.mapped_agent_name,
            "auth_username": request.auth_username,
            "auth_password": request.auth_password,
            "sip_address": request.sip_address,
            "status": "created"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database Logging Error: {str(e)}")


@app.post("/configure_sip/")
async def configure_sip(request: SIPRequest):
    db = get_database()  # Get the MongoDB database connection

    phone_number = request.phone_number
    provider = request.provider

    # Adjust phone number format based on provider
    if provider == "telnyx":
        if phone_number.startswith("+"):
            telnyx_inbound_number = phone_number[1:]  # Remove leading "+" for inbound trunk
            telnyx_outbound_number = phone_number  # Keep '+' for outbound trunk
        else:
            telnyx_inbound_number = phone_number
            telnyx_outbound_number = f"+{phone_number}"  # Add '+' for outbound trunk
    else:
        telnyx_inbound_number = phone_number
        telnyx_outbound_number = phone_number

    # Create a temporary directory for this request
    temp_dir = tempfile.mkdtemp()

    try:
        # Generate unique file names
        inbound_trunk_filename = f"inboundTrunk_{uuid.uuid4()}.json"
        inbound_trunk_path = os.path.join(temp_dir, inbound_trunk_filename)

        dispatch_rule_filename = f"dispatchRule_{uuid.uuid4()}.json"
        dispatch_rule_path = os.path.join(temp_dir, dispatch_rule_filename)

        outbound_trunk_filename = f"outboundTrunk_{uuid.uuid4()}.json"
        outbound_trunk_path = os.path.join(temp_dir, outbound_trunk_filename)

        # Step 1: Create the Inbound Trunk JSON file
        inbound_trunk_content = f"""
        {{
            "trunk": {{
                "name": "Demo Inbound Trunk",
                "numbers": ["{telnyx_inbound_number}"]
            }}
        }}
        """

        # Write the inbound trunk file
        with open(inbound_trunk_path, "w") as f:
            f.write(inbound_trunk_content)

        # Step 2: Run the lk command to create inbound trunk
        create_trunk_cmd = f"lk sip inbound create {inbound_trunk_path}"
        try:
            create_trunk_output = await run_command(create_trunk_cmd)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create inbound trunk: {str(e)}")

        # Extract the inbound trunk ID from the output
        inbound_trunk_id = ""
        for line in create_trunk_output.splitlines():
            if line.startswith("SIPTrunkID:"):
                inbound_trunk_id = line.split(":")[1].strip()
                break

        if not inbound_trunk_id:
            raise Exception("Failed to retrieve Inbound Trunk ID")

        # Step 3: Create the Dispatch Rule JSON file (dispatch to individual rooms)
        dispatch_rule_content = f"""
        {{
            "name": "Demo Dispatch Rule",
            "trunk_ids": ["{inbound_trunk_id}"],
            "rule": {{
                "dispatchRuleIndividual": {{
                    "roomPrefix": "call-"
                }}
            }}
        }}
        """

        with open(dispatch_rule_path, "w") as f:
            f.write(dispatch_rule_content)

        # Step 4: Run the lk command to create dispatch rule
        create_dispatch_cmd = f"lk sip dispatch create {dispatch_rule_path}"
        try:
            create_dispatch_output = await run_command(create_dispatch_cmd)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create dispatch rule: {str(e)}")

        # Extract the dispatch rule ID from the output
        dispatch_rule_id = ""
        for line in create_dispatch_output.splitlines():
            if line.startswith("SIPDispatchRuleID:"):
                dispatch_rule_id = line.split(":")[1].strip()
                break

        if not dispatch_rule_id:
            raise Exception("Failed to retrieve Dispatch Rule ID")

        # Step 5: Create the Outbound Trunk JSON file
        # Ensure that for Telnyx, the phone number includes '+'
        outbound_number = telnyx_outbound_number

        outbound_trunk_content = f"""
        {{
            "trunk": {{
                "name": "Demo Outbound Trunk",
                "address": "{request.sip_address}",
                "numbers": ["{outbound_number}"],
                "auth_username": "{request.auth_username}",
                "auth_password": "{request.auth_password}"
            }}
        }}
        """

        # Write the outbound trunk file
        with open(outbound_trunk_path, "w") as f:
            f.write(outbound_trunk_content)

        # Step 6: Run the lk command to create outbound trunk
        create_outbound_trunk_cmd = f"lk sip outbound create {outbound_trunk_path}"
        try:
            create_outbound_trunk_output = await run_command(create_outbound_trunk_cmd)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create outbound trunk: {str(e)}")

        # Extract the outbound trunk ID from the output
        outbound_trunk_id = ""
        for line in create_outbound_trunk_output.splitlines():
            if line.startswith("SIPTrunkID:"):
                outbound_trunk_id = line.split(":")[1].strip()
                break

        if not outbound_trunk_id:
            raise Exception("Failed to retrieve Outbound Trunk ID")

        # Step 7: Log the request into MongoDB
        await log_request_to_db(db, request, inbound_trunk_id, dispatch_rule_id, outbound_trunk_id)

        return {
            "message": "SIP trunks and dispatch rule created successfully.",
            "inbound_trunk_id": inbound_trunk_id,
            "dispatch_rule_id": dispatch_rule_id,
            "outbound_trunk_id": outbound_trunk_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pass
        # Clean up the temporary directory
        # shutil.rmtree(temp_dir)
# Endpoint to get all phone numbers and details associated with an email
@app.get("/get_phone_numbers/{email}")
async def get_phone_numbers(email: str):
    db = get_database()

    # Search for all records associated with the email
    results = db.logs.find({"email": email})

    # Convert cursor to a list and ensure it's not empty
    details = list(results)
    
    if not details:
        return {"email": email, "details": []}  # Return empty array if no records found

    # Prepare the response containing all details
    response = []
    for entry in details:
        response.append({
            "phone_number": entry.get("phone_number"),
            "provider": entry.get("provider"),
            "api_key": entry.get("api_key"),
            "api_secret": entry.get("api_secret"),
            "label": entry.get("label"),
            "mapped_agent_name": entry.get("mapped_agent_name"),
            "inbound_trunk_id": entry.get("inbound_trunk_id"),
            "outbound_trunk_id": entry.get("outbound_trunk_id"),
            "dispatch_rule_id": entry.get("dispatch_rule_id"),
            "auth_username": entry.get("auth_username"),      # Added field
            "auth_password": entry.get("auth_password"),      # Added field
            "sip_address": entry.get("sip_address"),          # Added field
            "status": entry.get("status")
        })

    return {"email": email, "details": response}

@app.put("/map_agent/")
async def map_agent(
    phone_number: str = Body(..., embed=True),
    email: str = Body(..., embed=True),
    agent_name: str = Body(..., embed=True)
):
    db = get_database()

    # Find the record to update based on phone number and email
    trunk_entry = db.logs.find_one({"phone_number": phone_number, "email": email})

    if not trunk_entry:
        raise HTTPException(status_code=404, detail="Phone number not found for the given email")

    # Update the mapped agent
    try:
        db.logs.update_one(
            {"phone_number": phone_number, "email": email},
            {"$set": {"mapped_agent_name": agent_name}}
        )
        return {"message": f"Agent '{agent_name}' mapped successfully to phone number {phone_number}."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to map agent: {str(e)}")

# Endpoint to delete the inbound trunk and dispatch rule by phone number
@app.delete("/delete_sip/{phone_number}")
async def delete_sip(phone_number: str, email: str):
    db = get_database()  # Get the MongoDB database connection

    # Search for the trunk entry in MongoDB using the phone number and email
    trunk_entry = db.logs.find_one({"phone_number": phone_number, "email": email})

    if not trunk_entry:
        raise HTTPException(status_code=404, detail="Trunk not found for the given email and phone number")

    inbound_trunk_id = trunk_entry.get("inbound_trunk_id")
    dispatch_rule_id = trunk_entry.get("dispatch_rule_id")
    outbound_trunk_id = trunk_entry.get("outbound_trunk_id")

    try:
        # Step 1: Delete the inbound trunk using lk command
        delete_trunk_cmd = f"lk sip inbound delete {inbound_trunk_id}"
        await run_command(delete_trunk_cmd)

        # Step 2: Delete the dispatch rule using lk command
        delete_dispatch_cmd = f"lk sip dispatch delete {dispatch_rule_id}"
        await run_command(delete_dispatch_cmd)

        # Step 3: Delete the outbound trunk using lk command
        delete_outbound_trunk_cmd = f"lk sip outbound delete {outbound_trunk_id}"
        await run_command(delete_outbound_trunk_cmd)

        # Step 4: Remove the trunk entry from MongoDB
        db.logs.delete_one({"phone_number": phone_number, "email": email})

        return {
            "message": f"SIP trunks and dispatch rule for {phone_number} deleted successfully."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Endpoint to update a specific trunk by phone number
@app.put("/update_sip/{phone_number}")
async def update_sip(
    phone_number: str,
    email: str = Body(..., embed=True),
    request: SIPRequest = Body(...)
):
    db = get_database()

    # Find the record to update
    trunk_entry = db.logs.find_one({"phone_number": phone_number, "email": email})

    if not trunk_entry:
        raise HTTPException(status_code=404, detail="Trunk not found")

    # Retrieve existing IDs
    inbound_trunk_id = trunk_entry.get("inbound_trunk_id")
    outbound_trunk_id = trunk_entry.get("outbound_trunk_id")
    dispatch_rule_id = trunk_entry.get("dispatch_rule_id")

    # Delete existing trunks and dispatch rules
    try:
        if inbound_trunk_id:
            delete_inbound_trunk_cmd = f"lk sip inbound delete {inbound_trunk_id}"
            await run_command(delete_inbound_trunk_cmd)
        if outbound_trunk_id:
            delete_outbound_trunk_cmd = f"lk sip outbound delete {outbound_trunk_id}"
            await run_command(delete_outbound_trunk_cmd)
        if dispatch_rule_id:
            delete_dispatch_rule_cmd = f"lk sip dispatch delete {dispatch_rule_id}"
            await run_command(delete_dispatch_rule_cmd)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete existing trunks or dispatch rule: {str(e)}")

    # Now create new trunks and dispatch rules similar to /configure_sip/
    # Adjust phone number format based on provider
    if request.provider == "telnyx":
        if phone_number.startswith("+"):
            telnyx_inbound_number = phone_number[1:]  # Remove leading "+" for inbound trunk
            telnyx_outbound_number = phone_number  # Keep '+' for outbound trunk
        else:
            telnyx_inbound_number = phone_number
            telnyx_outbound_number = f"+{phone_number}"  # Add '+' for outbound trunk
    else:
        telnyx_inbound_number = phone_number
        telnyx_outbound_number = phone_number

    # Create a temporary directory for this request
    temp_dir = tempfile.mkdtemp()

    try:
        # Generate unique file names
        inbound_trunk_filename = f"inboundTrunk_{uuid.uuid4()}.json"
        inbound_trunk_path = os.path.join(temp_dir, inbound_trunk_filename)

        dispatch_rule_filename = f"dispatchRule_{uuid.uuid4()}.json"
        dispatch_rule_path = os.path.join(temp_dir, dispatch_rule_filename)

        outbound_trunk_filename = f"outboundTrunk_{uuid.uuid4()}.json"
        outbound_trunk_path = os.path.join(temp_dir, outbound_trunk_filename)

        # Step 1: Create the Inbound Trunk JSON file
        inbound_trunk_content = f"""
        {{
            "trunk": {{
                "name": "Demo Inbound Trunk",
                "numbers": ["{telnyx_inbound_number}"]
            }}
        }}
        """

        # Write the inbound trunk file
        with open(inbound_trunk_path, "w") as f:
            f.write(inbound_trunk_content)

        # Step 2: Run the lk command to create inbound trunk
        create_trunk_cmd = f"lk sip inbound create {inbound_trunk_path}"
        try:
            create_trunk_output = await run_command(create_trunk_cmd)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create inbound trunk: {str(e)}")

        # Extract the inbound trunk ID from the output
        new_inbound_trunk_id = ""
        for line in create_trunk_output.splitlines():
            if line.startswith("SIPTrunkID:"):
                new_inbound_trunk_id = line.split(":")[1].strip()
                break

        if not new_inbound_trunk_id:
            raise Exception("Failed to retrieve new Inbound Trunk ID")

        # Step 3: Create the Dispatch Rule JSON file
        dispatch_rule_content = f"""
        {{
            "name": "Demo Dispatch Rule",
            "trunk_ids": ["{new_inbound_trunk_id}"],
            "rule": {{
                "dispatchRuleIndividual": {{
                    "roomPrefix": "call-"
                }}
            }}
        }}
        """

        with open(dispatch_rule_path, "w") as f:
            f.write(dispatch_rule_content)

        # Step 4: Run the lk command to create dispatch rule
        create_dispatch_cmd = f"lk sip dispatch create {dispatch_rule_path}"
        try:
            create_dispatch_output = await run_command(create_dispatch_cmd)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create dispatch rule: {str(e)}")

        # Extract the dispatch rule ID from the output
        new_dispatch_rule_id = ""
        for line in create_dispatch_output.splitlines():
            if line.startswith("SIPDispatchRuleID:"):
                new_dispatch_rule_id = line.split(":")[1].strip()
                break

        if not new_dispatch_rule_id:
            raise Exception("Failed to retrieve new Dispatch Rule ID")

        # Step 5: Create the Outbound Trunk JSON file
        outbound_number = telnyx_outbound_number

        outbound_trunk_content = f"""
        {{
            "trunk": {{
                "name": "Demo Outbound Trunk",
                "address": "{request.sip_address}",
                "numbers": ["{outbound_number}"],
                "auth_username": "{request.auth_username}",
                "auth_password": "{request.auth_password}"
            }}
        }}
        """

        # Write the outbound trunk file
        with open(outbound_trunk_path, "w") as f:
            f.write(outbound_trunk_content)

        # Step 6: Run the lk command to create outbound trunk
        create_outbound_trunk_cmd = f"lk sip outbound create {outbound_trunk_path}"
        try:
            create_outbound_trunk_output = await run_command(create_outbound_trunk_cmd)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create outbound trunk: {str(e)}")

        # Extract the outbound trunk ID from the output
        new_outbound_trunk_id = ""
        for line in create_outbound_trunk_output.splitlines():
            if line.startswith("SIPTrunkID:"):
                new_outbound_trunk_id = line.split(":")[1].strip()
                break

        if not new_outbound_trunk_id:
            raise Exception("Failed to retrieve new Outbound Trunk ID")

        # Update the MongoDB entry with new IDs and updated data
        update_data = {
            "api_key": request.api_key,
            "api_secret": request.api_secret,
            "label": request.label,
            "mapped_agent_name": request.mapped_agent_name,
            "auth_username": request.auth_username,
            "auth_password": request.auth_password,
            "sip_address": request.sip_address,
            "provider": request.provider,
            "inbound_trunk_id": new_inbound_trunk_id,
            "outbound_trunk_id": new_outbound_trunk_id,
            "dispatch_rule_id": new_dispatch_rule_id
        }

        db.logs.update_one(
            {"phone_number": phone_number, "email": email},
            {"$set": update_data}
        )

        return {
            "message": f"SIP configuration for phone number {phone_number} updated successfully.",
            "inbound_trunk_id": new_inbound_trunk_id,
            "outbound_trunk_id": new_outbound_trunk_id,
            "dispatch_rule_id": new_dispatch_rule_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update SIP configuration: {str(e)}")
    finally:
        pass
        # Clean up the temporary directory
        # shutil.rmtree(temp_dir)

@app.post("/test_outgoing_call/")
async def test_outgoing_call(
    email: str = Body(..., embed=True),
    agent_phone_number: str = Body(..., embed=True),
    phone_number_to_dial: str = Body(..., embed=True)
):
    db = get_database()  # Use your method to connect to MongoDB here

    # Find the agent using their phone number and email
    log_entry = db.logs.find_one({"email": email, "phone_number": agent_phone_number})
    
    if not log_entry:
        raise HTTPException(status_code=404, detail="Agent not found for the given email and phone number")
    
    # Retrieve the outbound trunk ID from the agent's log entry
    outbound_trunk_id = log_entry.get("outbound_trunk_id")
    if not outbound_trunk_id:
        raise HTTPException(status_code=404, detail="Outbound trunk ID not found")

    # Construct participant_identity for the call, including 'outbound'
    participant_identity = f"sip_{phone_number_to_dial.strip('+')}_outbound_test_call"

    # Create the SIP Participant JSON payload
    sip_participant_content = f"""
    {{
        "sip_trunk_id": "{outbound_trunk_id}",
        "sip_call_to": "{phone_number_to_dial}",
        "room_name": "call-{phone_number_to_dial.strip('+')}",
        "participant_identity": "{participant_identity}",
        "participant_name": "Test Call"
    }}
    """

    # Create a temporary directory and write the sipParticipant.json file
    temp_dir = tempfile.mkdtemp()
    sip_participant_filename = f"sipParticipant_{uuid.uuid4()}.json"
    sip_participant_path = os.path.join(temp_dir, sip_participant_filename)

    with open(sip_participant_path, "w") as f:
        f.write(sip_participant_content)

    # Run the lk command to create SIP Participant
    create_sip_participant_cmd = f"lk sip participant create {sip_participant_path}"
    try:
        subprocess.run(create_sip_participant_cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create SIP participant: {str(e)}")
    finally:
        shutil.rmtree(temp_dir)  # Clean up temporary files

    return {"detail": f"Outgoing call to {phone_number_to_dial} initiated successfully."}

def get_call_logs(user_id: str):
    # Get the database connection
    db = get_database()

    # Access the collection
    call_logs_collection = db["call_logs"]

    # Query the database for logs by user_id
    query = {'user_id': user_id}
    call_logs = list(call_logs_collection.find(query))
    
    if not call_logs:
        return []
    
    # Convert MongoDB-specific fields for FastAPI response
    for call_log in call_logs:
        if '_id' in call_log:
            call_log['_id'] = str(call_log['_id'])  # Convert ObjectId to string
        # Convert datetime fields to ISO format
        call_log['start_time'] = call_log['start_time'].isoformat() if 'start_time' in call_log else None
        call_log['end_time'] = call_log['end_time'].isoformat() if 'end_time' in call_log else None
        # Convert messages' timestamps
        if 'messages' in call_log:
            for message in call_log['messages']:
                if 'timestamp' in message:
                    message['timestamp'] = message['timestamp'].isoformat()
    
    return call_logs

# Helper function to get the time period filter
def get_time_filter(filter_type: str):
    now = datetime.now()
    if filter_type == "day":
        start_time = now - timedelta(days=1)
        previous_start_time = start_time - timedelta(days=1)
    elif filter_type == "week":
        start_time = now - timedelta(weeks=1)
        previous_start_time = start_time - timedelta(weeks=1)
    elif filter_type == "month":
        start_time = now - timedelta(days=30)
        previous_start_time = start_time - timedelta(days=30)
    else:
        start_time = None  # No time filter for overall
        previous_start_time = None
    return start_time, previous_start_time

# Helper function to calculate percentage change
def calculate_percentage_change(current, previous):
    if previous == 0:
        return 100 if current > 0 else 0
    return ((current - previous) / previous) * 100

# Helper function to fetch and aggregate data for a period
def fetch_combined_aggregated_data(user_id: str, start_time: datetime):
    db = get_database()

    # Access the collections
    call_logs_collection = db["call_logs"]
    chat_logs_collection = db["chat_logs"]

    # Build queries
    query = {'user_id': user_id}
    call_query = query.copy()
    chat_query = query.copy()
    if start_time:
        call_query['start_time'] = {'$gte': start_time}
        chat_query['created_at'] = {'$gte': start_time}

    # Fetch call logs and chat logs
    call_logs = list(call_logs_collection.find(call_query))
    chat_logs = list(chat_logs_collection.find(chat_query))

    # Initialize aggregated data
    total_conversation_minutes = 0
    total_spent = 0
    number_of_calls = len(call_logs)
    number_of_chats = len(chat_logs)
    total_tokens_llm = 0
    total_tokens_stt = 0
    total_tokens_tts = 0

    # Process call logs
    for log in call_logs:
        total_conversation_minutes += log['duration'] / 60  # Convert duration to minutes
        total_spent += log['total_cost']
        total_tokens_llm += log.get('total_tokens_llm', 0)
        total_tokens_stt += log.get('total_tokens_stt', 0)
        total_tokens_tts += log.get('total_tokens_tts', 0)

    # Process chat logs
    for log in chat_logs:
        # Estimate chat duration based on tokens (assuming 100 tokens ~ 1 minute)
        chat_tokens = log['total_tokens']
        chat_duration_minutes = chat_tokens / 100  # Adjust the divisor based on your estimation
        total_conversation_minutes += chat_duration_minutes
        total_spent += log['cost_llm']
        total_tokens_llm += chat_tokens
        # No STT or TTS tokens for chat logs

    # Compute average cost per conversation
    total_conversations = number_of_calls + number_of_chats
    avg_cost_per_conversation = total_spent / total_conversations if total_conversations > 0 else 0

    return {
        'total_conversation_minutes': total_conversation_minutes,
        'total_spent': total_spent,
        'number_of_calls': number_of_calls,
        'number_of_chats': number_of_chats,
        'total_conversations': total_conversations,
        'average_cost_per_conversation': avg_cost_per_conversation,
        'total_tokens_llm': total_tokens_llm,
        'total_tokens_stt': total_tokens_stt,
        'total_tokens_tts': total_tokens_tts
    }

# Dashboard API
@app.get("/dashboard/{user_id}/{filter_type}")
def get_dashboard(user_id: str, filter_type: str):
    db = get_database()

    # Validate filter_type
    if filter_type not in ["day", "week", "month", "overall"]:
        raise HTTPException(status_code=400, detail="Invalid filter type")

    # Get the time filter for the current and previous period
    start_time, previous_start_time = get_time_filter(filter_type)

    # Fetch current period data
    current_data = fetch_combined_aggregated_data(user_id, start_time)

    # Fetch previous period data for comparison
    if previous_start_time:
        previous_data = fetch_combined_aggregated_data(user_id, previous_start_time)
    else:
        previous_data = {
            'total_conversation_minutes': 0,
            'total_spent': 0,
            'number_of_calls': 0,
            'number_of_chats': 0,
            'total_conversations': 0,
            'average_cost_per_conversation': 0,
            'total_tokens_llm': 0,
            'total_tokens_stt': 0,
            'total_tokens_tts': 0
        }

    # Calculate percentage changes
    percentage_changes = {
        "total_conversation_minutes": calculate_percentage_change(current_data['total_conversation_minutes'], previous_data['total_conversation_minutes']),
        "number_of_conversations": calculate_percentage_change(current_data['total_conversations'], previous_data['total_conversations']),
        "total_spent": calculate_percentage_change(current_data['total_spent'], previous_data['total_spent']),
        "average_cost_per_conversation": calculate_percentage_change(current_data['average_cost_per_conversation'], previous_data['average_cost_per_conversation']),
    }

    # Fetch logs for the current period
    call_logs_collection = db["call_logs"]
    chat_logs_collection = db["chat_logs"]

    call_query = {'user_id': user_id}
    chat_query = {'user_id': user_id}
    if start_time:
        call_query['start_time'] = {'$gte': start_time}
        chat_query['created_at'] = {'$gte': start_time}

    call_logs = list(call_logs_collection.find(call_query))
    chat_logs = list(chat_logs_collection.find(chat_query))

    # Initialize variables for other statistics
    call_end_reasons = {}
    assistants_table = {}
    call_breakdown_by_category = {
        "call_counts": {"web": 0, "sip": 0},
        "call_durations": {"web": 0.0, "sip": 0.0},
        "total_spent": {"web": 0.0, "sip": 0.0}
    }
    cost_per_provider = {}
    cost_breakdown_by_agent = {}
    total_conversations_per_agent = {}
    average_call_duration_per_category = {"web": 0.0, "sip": 0.0}

    # Process call logs
    for log in call_logs:
        duration_minutes = log['duration'] / 60
        # Call end reason handling
        call_end_reason = log.get('call_end_reason', 'Completed')
        call_end_reasons[call_end_reason] = call_end_reasons.get(call_end_reason, 0) + 1

        # Assistant statistics
        assistant_name = log.get('agent_name', 'Unknown')
        if assistant_name not in assistants_table:
            assistants_table[assistant_name] = {
                "conversation_count": 0,
                "total_duration": 0.0,
                "total_cost": 0.0
            }
        assistants_table[assistant_name]['conversation_count'] += 1
        assistants_table[assistant_name]['total_duration'] += duration_minutes
        assistants_table[assistant_name]['total_cost'] += log['total_cost']

        # Category (web or sip) breakdown
        call_type = log['call_type']
        call_breakdown_by_category['call_counts'][call_type] += 1
        call_breakdown_by_category['call_durations'][call_type] += duration_minutes
        call_breakdown_by_category['total_spent'][call_type] += log['total_cost']

        # Provider cost breakdown
        provider = log.get('llm_name', 'Unknown')
        if provider not in cost_per_provider:
            cost_per_provider[provider] = 0.0
        cost_per_provider[provider] += log['total_cost']

        # Cost per agent
        if assistant_name not in cost_breakdown_by_agent:
            cost_breakdown_by_agent[assistant_name] = 0.0
        cost_breakdown_by_agent[assistant_name] += log['total_cost']

        # Conversations per agent
        if assistant_name not in total_conversations_per_agent:
            total_conversations_per_agent[assistant_name] = 0
        total_conversations_per_agent[assistant_name] += 1

    # Process chat logs
    for log in chat_logs:
        # Estimate duration based on tokens (assuming 100 tokens ~ 1 minute)
        chat_tokens = log['total_tokens']
        chat_duration_minutes = chat_tokens / 100
        assistant_name = log.get('agent_name', 'Unknown')
        if assistant_name not in assistants_table:
            assistants_table[assistant_name] = {
                "conversation_count": 0,
                "total_duration": 0.0,
                "total_cost": 0.0
            }
        assistants_table[assistant_name]['conversation_count'] += 1
        assistants_table[assistant_name]['total_duration'] += chat_duration_minutes
        assistants_table[assistant_name]['total_cost'] += log['cost_llm']

        # Provider cost breakdown
        provider = 'LLM'  # Assuming chat uses LLM
        if provider not in cost_per_provider:
            cost_per_provider[provider] = 0.0
        cost_per_provider[provider] += log['cost_llm']

        # Cost per agent
        if assistant_name not in cost_breakdown_by_agent:
            cost_breakdown_by_agent[assistant_name] = 0.0
        cost_breakdown_by_agent[assistant_name] += log['cost_llm']

        # Conversations per agent
        if assistant_name not in total_conversations_per_agent:
            total_conversations_per_agent[assistant_name] = 0
        total_conversations_per_agent[assistant_name] += 1

    # Calculate average call duration per category
    for category in average_call_duration_per_category.keys():
        call_count = call_breakdown_by_category['call_counts'][category]
        if call_count > 0:
            average_call_duration_per_category[category] = call_breakdown_by_category['call_durations'][category] / call_count

    # Calculate the final structure for the assistants table
    assistants_table_final = []
    for assistant_name, stats in assistants_table.items():
        avg_duration = stats['total_duration'] / stats['conversation_count'] if stats['conversation_count'] > 0 else 0
        assistants_table_final.append({
            "assistant_name": assistant_name,
            "conversation_count": stats['conversation_count'],
            "avg_duration": avg_duration,
            "total_cost": stats['total_cost']
        })

    # Calculate overall average cost per conversation
    average_cost_per_conversation = current_data['total_spent'] / current_data['total_conversations'] if current_data['total_conversations'] > 0 else 0

    # Return the final result
    return {
        "total_conversation_minutes": current_data['total_conversation_minutes'],
        "number_of_calls": current_data['number_of_calls'],
        "number_of_chats": current_data['number_of_chats'],
        "total_conversations": current_data['total_conversations'],
        "total_spent": current_data['total_spent'],
        "average_cost_per_conversation": average_cost_per_conversation,
        "percentage_changes": percentage_changes,
        "call_end_reasons": call_end_reasons,
        "average_call_duration_by_assistant": {
            name: stats['total_duration'] / stats['conversation_count'] if stats['conversation_count'] > 0 else 0
            for name, stats in assistants_table.items()
        },
        "cost_per_provider": cost_per_provider,
        "assistants_table": assistants_table_final,
        "total_conversations_per_agent": total_conversations_per_agent,
        "call_breakdown_by_category": call_breakdown_by_category,
        "total_tokens_used": {
            "total_tokens_llm": current_data['total_tokens_llm'],
            "total_tokens_stt": current_data['total_tokens_stt'],
            "total_tokens_tts": current_data['total_tokens_tts']
        },
        "cost_breakdown_by_agent": cost_breakdown_by_agent,
        "average_call_duration_per_category": average_call_duration_per_category
    }#---------jwt token------
@app.get("/generate-token")
async def generate_token(request: Request):
    try:
        # Extract query parameters from the URL
        phone = request.query_params.get('phone')
        id = request.query_params.get('id')
        # Validate if the required parameters are present
        if not phone or not id:
            raise HTTPException(status_code=400, detail="Missing required query parameters")

        room_name = phone
        identity = f"web_{id}"  # Interpolating ID for identity

        # Generate the LiveKit AccessToken using the Python LiveKit SDK
        token = api.AccessToken() \
            .with_identity(identity) \
            .with_name(f"User {identity}") \
            .with_grants(api.VideoGrants(
                room_join=True,
                room=room_name+"_id_"+str(str(uuid.uuid4())),
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True
            )).to_jwt()

        # Return the identity and access token as a JSON response
        return {
            "identity": identity,
            "accessToken": token
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Function to get agent name from agent_id
def get_agent_name(agent_id):
    db = get_database()
    users_collection = db["users"] 
    user = users_collection.find_one({"agents.id": agent_id}, {"agents.$": 1})
    if user and 'agents' in user and len(user['agents']) > 0:
        agent = user['agents'][0]
        return agent.get('agent_name', None)
    return None
# POST API for chat interaction
@app.post("/chat/")
def chat_interaction(chat_request: ChatRequest):
    """
    API to interact with the chat agent, pass the conversation to OpenAI, and log the interaction.
    """
    db = get_database()
    chat_logs_collection = db["chat_logs"]
    try:
        # Convert Pydantic ChatMessage objects to dictionaries
        chat_data = [message.dict() for message in chat_request.chat]  # Serialize to dictionaries

        # Call the openai_LLM function to process the chat
        result = openai_LLM(chat_data)  # Pass serialized chat data
        if not result:
            raise HTTPException(status_code=500, detail="Error with the LLM response.")

        content = result['choices'][0]['message']['content']
        usage = result['usage']

        # Calculate total tokens and cost
        total_tokens = usage.get('total_tokens', 0)
        cost_llm = total_tokens * 0.00002

        # Get agent name
        agent_name = get_agent_name(chat_request.agent_id)

        # Prepare the log data
        log_data = {
            "chat_data": chat_data,  # Save the serialized chat data
            "result": content,
            "usage": usage,
            "total_tokens": total_tokens,
            "cost_llm": cost_llm,
            "agent_id": chat_request.agent_id,
            "agent_name": agent_name,
            "user_id": chat_request.user_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        if chat_request.chat_id:
            # Update existing chat log
            existing_log = chat_logs_collection.find_one({"chat_id": chat_request.chat_id})
            if existing_log:
                # Append new messages
                updated_chat_data = existing_log['chat_data'] + chat_data
                total_tokens += existing_log.get('total_tokens', 0)
                cost_llm += existing_log.get('cost_llm', 0.0)
                chat_logs_collection.update_one(
                    {"chat_id": chat_request.chat_id},
                    {
                        "$set": {
                            "chat_data": updated_chat_data,
                            "result": content,
                            "usage": usage,
                            "total_tokens": total_tokens,
                            "cost_llm": cost_llm,
                            "updated_at": datetime.utcnow()
                        }
                    }
                )
                chat_id = chat_request.chat_id
            else:
                # Create new chat log with provided chat_id
                log_data["chat_id"] = chat_request.chat_id
                chat_logs_collection.insert_one(log_data)
                chat_id = chat_request.chat_id
        else:
            # Create new chat log
            chat_id = str(uuid.uuid4())
            log_data["chat_id"] = chat_id
            chat_logs_collection.insert_one(log_data)

        # Return the response including agent name
        return {
            "chat_id": chat_id,
            "response": content,
            "agent_name": agent_name
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

    
@app.get("/call_logs/{user_id}", response_model=List[CallLog])
def get_call_logs(user_id: str):
    # Get the database connection
    db = get_database()

    # Access the collection
    call_logs_collection = db["call_logs"]
    
    # Query the database for logs by user_id
    query = {'user_id': user_id}
    call_logs = list(call_logs_collection.find(query))
    if not call_logs:
        return []
    
    # Convert MongoDB-specific fields for FastAPI response
    for call_log in call_logs:
        if '_id' in call_log:
            call_log['_id'] = str(call_log['_id'])  # Convert ObjectId to string
        
        # Ensure the called_number is correctly formatted
        call_log['called_number'] = call_log.get('called_number', 'N/A')  # Default to 'N/A' if not present
        
        # Ensure the call_direction is set, default to 'unknown' if not present
        call_log['call_direction'] = call_log.get('call_direction', 'unknown')  # Default to 'unknown' if not present

        # Convert datetime fields to ISO format
        call_log['start_time'] = call_log['start_time'].isoformat() if 'start_time' in call_log else None
        call_log['end_time'] = call_log['end_time'].isoformat() if 'end_time' in call_log else None

        # Convert messages' timestamps
        if 'messages' in call_log:
            for message in call_log['messages']:
                if 'timestamp' in message:
                    message['timestamp'] = message['timestamp'].isoformat()
    return call_logs

# GET API to fetch chat logs
@app.get("/chat_logs/")
def get_chat_logs(
    user_id: str = Query(..., description="User ID"),
    agent_id: Optional[str] = Query(None, description="Agent ID"),
    chat_id: Optional[str] = Query(None, description="Chat ID")
):
    db = get_database()
    chat_logs_collection = db["chat_logs"]
 # To fetch agent name
    """API to fetch chat logs from MongoDB"""
    query = {"user_id": user_id}
    if agent_id:
        query["agent_id"] = agent_id
    if chat_id:
        query["chat_id"] = chat_id

    logs = list(chat_logs_collection.find(query))
    if not logs:
        raise HTTPException(status_code=404, detail="No logs found")

    # Prepare the response
    response_logs = []
    for log in logs:
        log["_id"] = str(log["_id"])
        response_logs.append(log)

    return response_logs

@app.post("/save_data/")
def save_dynamic_data(request: DynamicDataRequest):
    try:
        db = get_database()
        dynamic_data_collection = db["dynamic_data"]
        # Store dynamic data with user_id and agent_id
        data_to_save = {
            "user_id": request.user_id,
            "agent_id": request.agent_id,
            "data": request.data
        }
        
        # Insert the data into MongoDB
        dynamic_data_collection.insert_one(data_to_save)
        
        return {"message": "Data saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving data: {e}")

# GET API: Retrieve all dynamic data for a specific user and agent
@app.get("/get_data/")
def get_all_dynamic_data(user_id: str, agent_id: str):
    try:
        db = get_database()
        dynamic_data_collection = db["dynamic_data"]
        # Query MongoDB to retrieve all documents for the user and agent
        results = dynamic_data_collection.find(
            {"user_id": user_id, "agent_id": agent_id}, {"_id": 0, "data": 1}
        )
        
        # Convert the cursor to a list
        data_list = list(results)

        if not data_list:
            raise HTTPException(status_code=404, detail="No data found")
        
        return {"data": data_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving data: {e}")

# API to generate CSV from stored dynamic data and delete old CSV if it exists
@app.get("/generate_csv/")
def generate_csv(user_id: str, agent_id: str):
    try:
        db = get_database()
        dynamic_data_collection = db["dynamic_data"]
        # Query MongoDB to retrieve all documents for the user and agent
        results = dynamic_data_collection.find(
            {"user_id": user_id, "agent_id": agent_id}, {"_id": 0, "data": 1}
        )
        
        data_list = list(results)  # Convert cursor to a list
        
        if not data_list:
            raise HTTPException(status_code=404, detail="Data not found")
        
        # CSV file name based on user_id and agent_id
        csv_filename = f"{user_id}_{agent_id}.csv"
        csv_filepath = os.path.join(CSV_DIR, csv_filename)
        
        # Check if the file already exists and delete it
        if os.path.exists(csv_filepath):
            os.remove(csv_filepath)
        
        # Collect all unique keys to use as headers for the CSV
        all_keys = set()
        for data_entry in data_list:
            all_keys.update(data_entry["data"].keys())
        
        # Write data to CSV
        with open(csv_filepath, mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(all_keys))
            writer.writeheader()  # Write CSV header
            
            # Write each data entry as a row in the CSV
            for data_entry in data_list:
                writer.writerow(data_entry["data"])
        
        # Return the CSV file link
        return {"csv_link": f"/download_csv/{csv_filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating CSV: {e}")

# API to download CSV file
@app.get("/download_csv/{csv_filename}")
def download_csv(csv_filename: str):
    csv_filepath = os.path.join(CSV_DIR, csv_filename)
    
    if not os.path.exists(csv_filepath):
        raise HTTPException(status_code=404, detail="CSV file not found")
    
    return FileResponse(csv_filepath, media_type="text/csv", filename=csv_filename)

# ------------------- Campaign Endpoints -------------------

# 1. Create a Campaign
@app.post("/campaigns/", response_model=Campaign)
def create_campaign(campaign_create: CampaignCreate, db=Depends(get_db)):
    campaign_id = str(uuid.uuid4())
    campaign_data = campaign_create.dict()
    campaign_data['campaign_id'] = campaign_id
    campaign_data['phone_numbers'] = []
    campaign_data['called_numbers'] = []
    campaign_data['status'] = 'created'
    campaign_data['created_at'] = datetime.utcnow()
    campaign_data['updated_at'] = datetime.utcnow()

    db.campaigns.insert_one(campaign_data)
    return Campaign(**campaign_data)

# 2. Get All Campaigns for a User
@app.get("/campaigns/")
def get_campaigns(email: str = Query(...), db=Depends(get_db)):
    campaigns = list(db.campaigns.find({"email": email}))
    if not campaigns:
        return {"email": email, "campaigns": []}

    campaign_list = []
    for campaign in campaigns:
        campaign_list.append({
            "campaign_id": campaign.get("campaign_id"),
            "campaign_name": campaign.get("campaign_name"),
            "campaign_description": campaign.get("campaign_description"),
            "agent_phone_number": campaign.get("agent_phone_number"),
            "status": campaign.get("status"),
            "created_at": campaign.get("created_at"),
            "updated_at": campaign.get("updated_at")
        })
    return {"email": email, "campaigns": campaign_list}

# 3. Update Campaign
@app.put("/campaigns/{campaign_id}/")
def update_campaign(
    campaign_id: str,
    campaign_update: CampaignUpdate = Body(...),
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    update_data = campaign_update.dict(exclude_unset=True)
    update_data['updated_at'] = datetime.utcnow()

    db.campaigns.update_one(
        {"campaign_id": campaign_id, "email": email},
        {"$set": update_data}
    )

    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    return Campaign(**campaign)

# 4. Delete Campaign
@app.delete("/campaigns/{campaign_id}/")
def delete_campaign(
    campaign_id: str,
    email: str = Query(...),
    db=Depends(get_db)
):
    result = db.campaigns.delete_one({"campaign_id": campaign_id, "email": email})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")
    else:
        return {"detail": "Campaign deleted"}

# 5. Import CSV for a Campaign
@app.post("/campaigns/{campaign_id}/import_csv/")
async def import_csv_for_campaign(
    campaign_id: str,
    email: str = Query(...),
    file: UploadFile = File(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    content = await file.read()
    decoded_content = content.decode('utf-8')
    reader = csv.DictReader(io.StringIO(decoded_content))

    phone_numbers = []
    for row in reader:
        phone_number = row.get('phone_number')
        if phone_number:
            phone_numbers.append(phone_number.strip())

    db.campaigns.update_one(
        {"campaign_id": campaign_id, "email": email},
        {"$addToSet": {"phone_numbers": {"$each": phone_numbers}}, "$set": {"updated_at": datetime.utcnow()}}
    )

    return {"detail": f"{len(phone_numbers)} phone numbers added to campaign"}

# 6. Add Manual Phone Numbers to a Campaign
@app.post("/campaigns/{campaign_id}/add_numbers/")
def add_phone_numbers_to_campaign(
    campaign_id: str,
    phone_numbers: List[str] = Body(...),
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    db.campaigns.update_one(
        {"campaign_id": campaign_id, "email": email},
        {"$addToSet": {"phone_numbers": {"$each": phone_numbers}}, "$set": {"updated_at": datetime.utcnow()}}
    )

    return {"detail": f"{len(phone_numbers)} phone numbers added to campaign"}

# 7. Delete Phone Number from Campaign
@app.delete("/campaigns/{campaign_id}/phone_numbers/")
def delete_phone_number_from_campaign(
    campaign_id: str,
    request: PhoneNumberDeleteRequest = Body(...),
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    phone_number = request.phone_number.strip()
    result = db.campaigns.update_one(
        {"campaign_id": campaign_id, "email": email},
        {
            "$pull": {
                "phone_numbers": phone_number,
                "called_numbers": phone_number
            },
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Phone number not found in campaign")
    else:
        return {"detail": f"Phone number {phone_number} deleted from campaign"}

# 8. Update Phone Number in Campaign
@app.put("/campaigns/{campaign_id}/phone_numbers/")
def update_phone_number_in_campaign(
    campaign_id: str,
    request: PhoneNumberUpdateRequest = Body(...),
    email: str = Query(...),
    db=Depends(get_db)
):
    # Fetch the campaign
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    old_phone_number = request.old_phone_number.strip()
    new_phone_number = request.new_phone_number.strip()

    # Ensure that the old phone number exists in the campaign
    if old_phone_number not in campaign.get('phone_numbers', []):
        raise HTTPException(status_code=404, detail="Old phone number not found in campaign")

    try:
        # Step 1: Remove the old phone number using $pull
        db.campaigns.update_one(
            {"campaign_id": campaign_id, "email": email},
            {"$pull": {"phone_numbers": old_phone_number}}
        )

        # Step 2: Add the new phone number using $addToSet
        db.campaigns.update_one(
            {"campaign_id": campaign_id, "email": email},
            {"$addToSet": {"phone_numbers": new_phone_number}}
        )

        # Update the called_numbers array if necessary
        if old_phone_number in campaign.get('called_numbers', []):
            db.campaigns.update_one(
                {"campaign_id": campaign_id, "email": email},
                {
                    "$pull": {"called_numbers": old_phone_number},
                    "$addToSet": {"called_numbers": new_phone_number}
                }
            )

        return {"detail": f"Phone number {old_phone_number} updated to {new_phone_number} in campaign"}

    except pymongo.errors.WriteError as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

# 9. Start Campaign
@app.post("/campaigns/{campaign_id}/start/")
def start_campaign(
    campaign_id: str,
    background_tasks: BackgroundTasks,
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    # Trigger the background task to process campaign calls
    background_tasks.add_task(process_campaign_calls_sync, campaign_id, email)
    return {"detail": "Campaign started"}
# 10. Get Campaign Details
@app.get("/campaigns/{campaign_id}/")
def get_campaign_details(
    campaign_id: str,
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    return Campaign(**campaign)

# 11. Get Call Status for a Phone Number in a Campaign
@app.get("/campaigns/{campaign_id}/call_status/")
def get_call_status(
    campaign_id: str,
    phone_number: str = Query(...),
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    phone_numbers = campaign.get('phone_numbers', [])
    called_numbers = campaign.get('called_numbers', [])

    if phone_number not in phone_numbers:
        raise HTTPException(status_code=404, detail="Phone number not found in campaign")

    status = "called" if phone_number in called_numbers else "pending"

    return {
        "campaign_id": campaign_id,
        "phone_number": phone_number,
        "status": status
    }
#12
# 12. Get Campaign Status
@app.get("/campaigns/{campaign_id}/status/")
def get_campaign_status(
    campaign_id: str,
    email: str = Query(...),
    db=Depends(get_db)
):
    campaign = db.campaigns.find_one({"campaign_id": campaign_id, "email": email})
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found or does not belong to user")

    return {
        "campaign_id": campaign_id,
        "status": campaign.get("status"),
        "updated_at": campaign.get("updated_at")
    }



def run():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)