from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from datetime import datetime


class ChatQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000, description="User's question or query")


class ChatResponse(BaseModel):
    response: str = Field(..., description="AI-generated response")
    sources: List[Dict[str, Any]] = Field(default=[], description="Source documents/chunks used")
    chat_id: Optional[str] = Field(None, description="ID of the chat session")


class DocumentProcessingResponse(BaseModel):
    success: bool = Field(..., description="Whether processing was successful")
    message: str = Field(..., description="Processing result message")
    document_id: str = Field(..., description="ID of the processed document")


class DocumentChunkResponse(BaseModel):
    id: str = Field(..., description="Chunk ID")
    chunk_index: int = Field(..., description="Order of chunk in document")
    text: str = Field(..., description="Chunk text content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional chunk metadata")


class DocumentChunksResponse(BaseModel):
    document_id: str = Field(..., description="Document ID")
    chunks: List[DocumentChunkResponse] = Field(..., description="List of document chunks")
    total_chunks: int = Field(..., description="Total number of chunks")


class ChatSessionResponse(BaseModel):
    id: str = Field(..., description="Chat session ID")
    query: str = Field(..., description="User's query")
    response: str = Field(..., description="AI response")
    created_at: str = Field(..., description="Creation timestamp")
    sources_count: int = Field(..., description="Number of sources used")


class ChatHistoryResponse(BaseModel):
    chat_sessions: List[ChatSessionResponse] = Field(..., description="List of chat sessions")
    total_sessions: int = Field(..., description="Total number of chat sessions")


class AIServiceStatusResponse(BaseModel):
    ai_service_ready: bool = Field(..., description="Whether AI service is ready")
    embedding_model: Optional[str] = Field(None, description="Name of loaded embedding model")
    status: str = Field(..., description="Service status")
    error: Optional[str] = Field(None, description="Error message if any")
