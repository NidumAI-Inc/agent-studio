from typing import List, Optional,Dict, Any
from pydantic import BaseModel, Field, constr
from datetime import datetime

class UserCreate(BaseModel):
    email: str

class UserUpdate(BaseModel):
    email: Optional[str] = None

class AgentCreate(BaseModel):
    agent_name: Optional[str] = "Ava"  # Default agent name if not provided
    phone_number: str
    LLM_provider: Optional[str] = "openai"  # New field, default value
    LLM_model: Optional[str] = "GPT 3.5 Turbo Cluster"  # New field, default value
    stt_provider: Optional[str] = "google"  # New field, default value
    stt_model: Optional[str] = "whisper"  # New field, default value
    rag_enabled: Optional[bool] = True  # Default RAG enabled status
    temperature: Optional[float] = 0.7  # Default temperature
    max_tokens: Optional[int] = 250  # Default max tokens
    first_message: Optional[str] = "Hello, this is Ava. How may I assist you today?"  # Default message
    system_prompt: Optional[str] = """Ava is a sophisticated AI training assistant, crafted by experts in customer support and AI development.
    Designed with the persona of a seasoned customer support agent in her early 30s, Ava combines deep technical knowledge with a strong sense of emotional intelligence.
    Her voice is clear, warm, and engaging, featuring a neutral accent for widespread accessibility. Ava's primary role is to serve as a dynamic training platform for customer support agents,
    simulating a broad array of service scenarios—from basic inquiries to intricate problem-solving challenges."""  # Default system prompt
    language: Optional[str] = "English"  # Default language
    voice: Optional[str] = "nova"  # Default voice
    TTS_provider: Optional[str] = "aws_polly"
    background_noise: Optional[str] = None
    agent_type: Optional[str] = "web"
    tts_speed: Optional[float] = 1.0
    interrupt_speech_duration: Optional[float] = 0.0

class AgentUpdate(BaseModel):
    phone_number: Optional[str] = None
    LLM_provider: Optional[str] = None  # New field
    LLM_model: Optional[str] = None  # New field
    stt_provider: Optional[str] = None  # New field
    stt_model: Optional[str] = None  # New field
    knowledge_base: Optional[dict] = None
    rag_enabled: Optional[bool] = None  # New field
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    first_message: Optional[str] = None
    system_prompt: Optional[str] = None
    language: Optional[str] = None
    voice: Optional[str] = None
    TTS_provider: Optional[str] = None
    background_noise: Optional[str] = None
    agent_name: Optional[str] = None
    tts_speed: Optional[float] = None
    interrupt_speech_duration: Optional[float] = None 

class KnowledgeBaseResponse(BaseModel):
    files: List[str]
    raw_data_file: Optional[str] = None
    pkl_file: Optional[str] = None
    vdb_data_file: Optional[str] = None

class FileListResponse(BaseModel):
    files: List[str]

class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender, e.g., 'user' or 'assistant'.")
    content: str = Field(..., description="Content of the message.")

class ChatRequest(BaseModel):
    agent_id: str = Field(..., description="ID of the agent")
    user_id: str = Field(..., description="ID of the user")
    chat: List[ChatMessage] = Field(..., description="List of messages exchanged")
    chat_id: Optional[str] = Field(None, description="Chat ID for existing chats (optional)")

class ChatLog(BaseModel):
    chat_id: str
    agent_id: str
    agent_name: Optional[str] = None
    user_id: str
    chat_data: List[ChatMessage]
    result: str
    usage: dict
    total_tokens: int
    cost_llm: float
    conversation_analysis: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class DynamicDataRequest(BaseModel):
    user_id: str
    agent_id: str
    data: Dict[str, Any]  # Accepting any dynamic JSON data


class CampaignCreate(BaseModel):
    email: str
    campaign_name: str
    campaign_description: Optional[str] = None
    agent_phone_number: str

class CampaignUpdate(BaseModel):
    campaign_name: Optional[str] = None
    campaign_description: Optional[str] = None
    agent_phone_number: Optional[str] = None

class Campaign(BaseModel):
    campaign_id: str
    email: str
    campaign_name: str
    campaign_description: Optional[str] = None
    agent_phone_number: str
    phone_numbers: List[str] = []
    called_numbers: List[str] = []
    status: str
    created_at: datetime
    updated_at: datetime

class PhoneNumberDeleteRequest(BaseModel):
    phone_number: str

class PhoneNumberUpdateRequest(BaseModel):
    old_phone_number: str
    new_phone_number: str