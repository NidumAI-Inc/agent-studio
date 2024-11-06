from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class KnowledgeBase(BaseModel):
    files: List[str]

class AI_Agent(BaseModel):
    id: str
    phone_number: str
    LLM_provider: str  # New field
    LLM_model: str  # New field
    stt_provider: str  # New field
    stt_model: str  # New field
    knowledge_base: KnowledgeBase
    rag_enabled: bool  # New field
    temperature: float
    max_tokens: int
    first_message: str
    system_prompt: str
    language: str
    voice: str
    agent_name: str
    TTS_provider: str
    background_noise: Optional[str] = None
    agent_type: str
    tts_speed: Optional[float] = 1.0  # Default TTS speed
    interrupt_speech_duration: Optional[float] = 0.0  # Default interrupt speech duration

class User(BaseModel):
    id: str = Field(alias="_id")
    email: str
    agents: List[AI_Agent] = []

class Message(BaseModel):
    timestamp: datetime
    speaker: str
    message: str
    tokens: int

class CallLog(BaseModel):
    call_log_id: str
    agent_id: Optional[str]
    agent_name: Optional[str]
    agent_phone_number: Optional[str]
    user_id: Optional[str]
    incoming_callerid: Optional[str]
    call_type: str
    start_time: datetime
    end_time: datetime
    duration: float
    messages: List[Message]
    tts_name: Optional[str]
    stt_name: Optional[str]
    llm_name: Optional[str]
    total_tokens_llm: int
    total_tokens_stt: int
    total_tokens_tts: int
    cost_llm: float
    cost_stt: float
    cost_tts: float
    platform_cost: float
    total_cost: float
    conversation_analysis: Optional[str]
    called_number: Optional[str]  
    call_direction: Optional[str] 

class DashboardData(BaseModel):
    total_call_minutes: float
    number_of_calls: int
    total_spent: float
    average_cost_per_call: float
    percentage_changes: dict
    call_end_reasons: dict
    average_call_duration_by_assistant: dict
    cost_per_provider: dict
    assistants_table: List[dict]
    total_calls_per_agent: dict
    call_breakdown_by_category: dict
    total_tokens_used: dict
    cost_breakdown_by_agent: dict
    average_call_duration_per_category: dict