import logging
import os
import time
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
# from sqlalchemy import text  # No longer needed - we don't use raw SQL queries
import openai
from dotenv import load_dotenv

# Load environment variables from project root
import os
from pathlib import Path

# The .env file is in the parent directory of backend
env_path = Path(__file__).parent.parent.parent.parent / ".env"

# Force reload environment variables
load_dotenv(env_path, override=True)

logger = logging.getLogger(__name__)
logger.info(f"Loading .env from: {env_path}")
logger.info(f".env file exists: {env_path.exists()}")

class AIService:
    def __init__(self):
        """Initialize AI service with OpenAI API"""
        self.openai_client = None
        self.initialization_status = "initializing"
        self.initialization_progress = 0
        self.initialization_message = "Setting up OpenAI API..."
        
        # Model configuration - users can change these later
        self.embedding_model = "text-embedding-3-small"  # Latest OpenAI embedding model (better performance)
        self.chat_model = "gpt-4o-mini"  # Default chat model for chat/discussion flows
        self.writing_model = "gpt-5-mini"  # Dedicated model for LaTeX editor writing tools

        # Provider configuration
        self.current_provider = "openai"  # Current AI provider
        self.available_providers = {
            "openai": {
                "name": "OpenAI",
                "embedding_models": ["text-embedding-ada-002", "text-embedding-3-small", "text-embedding-3-large"],
                "chat_models": [
                    "gpt-4o-mini",
                    "gpt-5-mini",
                    "gpt-5",
                    "gpt-4o-mini",           # Latest GPT-4o mini (fastest, cheapest)
                    "gpt-4o",                 # Latest GPT-4o (most capable)
                    "gpt-4o-2024-05-13",     # Specific GPT-4o version
                    "gpt-4-turbo",            # GPT-4 Turbo
                    "gpt-4-turbo-2024-04-09", # Specific GPT-4 Turbo version
                    "gpt-4",                  # Standard GPT-4
                    "gpt-4-0613",            # Specific GPT-4 version
                    "gpt-3.5-turbo",         # GPT-3.5 Turbo
                    "gpt-3.5-turbo-0125"     # Specific GPT-3.5 Turbo version
                ]
            },
            "openrouter": {
                "name": "OpenRouter",
                "embedding_models": ["text-embedding-ada-002", "text-embedding-3-small"],
                "chat_models": [
                    # OpenAI models via OpenRouter
                    "openai/gpt-4o-mini",
                    "openai/gpt-4o",
                    "openai/gpt-4-turbo",
                    "openai/gpt-4",
                    "openai/gpt-3.5-turbo",
                    # Anthropic models via OpenRouter
                    "anthropic/claude-3-5-sonnet-20241022",
                    "anthropic/claude-3-5-haiku-20241022",
                    "anthropic/claude-3-opus-20240229",
                    "anthropic/claude-3-sonnet-20240229",
                    "anthropic/claude-3-haiku-20240307",
                    # Meta models via OpenRouter
                    "meta-llama/llama-3.1-8b-instruct",
                    "meta-llama/llama-3.1-70b-instruct",
                    "meta-llama/llama-3.1-405b-instruct",
                    # Google models via OpenRouter
                    "google/gemini-pro",
                    "google/gemini-flash-1.5",
                    # Mistral models via OpenRouter
                    "mistralai/mistral-7b-instruct",
                    "mistralai/mixtral-8x7b-instruct",
                    "mistralai/mistral-large-latest"
                ]
            },
            "anthropic": {
                "name": "Anthropic",
                "embedding_models": ["text-embedding-ada-002"],  # Placeholder
                "chat_models": [
                    "claude-3-5-sonnet-20241022",  # Latest Claude 3.5 Sonnet
                    "claude-3-5-haiku-20241022",   # Latest Claude 3.5 Haiku
                    "claude-3-opus-20240229",      # Claude 3 Opus
                    "claude-3-sonnet-20240229",    # Claude 3 Sonnet
                    "claude-3-haiku-20240307"     # Claude 3 Haiku
                ]
            },
            "google": {
                "name": "Google",
                "embedding_models": ["text-embedding-ada-002"],  # Placeholder
                "chat_models": [
                    "gemini-1.5-pro",
                    "gemini-1.5-flash",
                    "gemini-1.0-pro",
                    "gemini-1.0-pro-vision"
                ]
            },
            "meta": {
                "name": "Meta",
                "embedding_models": ["text-embedding-ada-002"],  # Placeholder
                "chat_models": [
                    "llama-3.1-8b-instruct",
                    "llama-3.1-70b-instruct",
                    "llama-3.1-405b-instruct"
                ]
            }
        }
        
        try:
            # Initialize OpenAI client
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key or "your-openai-api-key-here" in api_key or api_key.startswith("sk-your_"):
                # For development/testing, provide mock responses
                self.initialization_status = "ready"
                self.initialization_progress = 100
                self.initialization_message = "AI Service Ready (Mock Mode - No OpenAI API Key)"
                logger.info("AI Service initialized in mock mode")
                return
            
            logger.info(f"API Key loaded: {api_key[:20]}...")
            
            # Initialize OpenAI client
            self.openai_client = openai.OpenAI(api_key=api_key)
            
            # Test the connection
            self._test_openai_connection()
            
            self.initialization_status = "ready"
            self.initialization_progress = 100
            self.initialization_message = "OpenAI API ready"
            logger.info("OpenAI API initialized successfully")
            
        except Exception as e:
            self.initialization_status = "error"
            self.initialization_message = f"Failed to initialize OpenAI API: {str(e)}"
            logger.error(f"Failed to initialize OpenAI API: {str(e)}")

    def _test_openai_connection(self):
        """Test OpenAI API connection with a simple request"""
        try:
            self.create_response(
                messages=[{"role": "user", "content": "Hello"}],
                max_output_tokens=32,
            )
            logger.info("OpenAI API connection test successful")
        except Exception as e:
            raise Exception(f"OpenAI API connection test failed: {str(e)}")

    def format_messages_for_responses(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize chat messages for the Responses API."""
        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            # Responses API accepts either a string or list of content blocks.
            normalized.append(
                {
                    "role": role,
                    "content": content,
                }
            )
        return normalized

    def create_response(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        **extra_params: Any,
    ):
        """Create a response using the new OpenAI Responses API."""
        if not self.openai_client:
            raise ValueError("OpenAI client is not configured")

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "input": self.format_messages_for_responses(messages),
        }
        target_model = payload["model"]

        if temperature is not None and self._supports_sampling_params(target_model):
            payload["temperature"] = temperature
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        payload.update({k: v for k, v in extra_params.items() if v is not None})

        return self.openai_client.responses.create(**payload)

    def stream_response(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        **extra_params: Any,
    ):
        """Stream a response using the OpenAI Responses API."""
        if not self.openai_client:
            raise ValueError("OpenAI client is not configured")

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "input": self.format_messages_for_responses(messages),
        }
        target_model = payload["model"]
        if temperature is not None and self._supports_sampling_params(target_model):
            payload["temperature"] = temperature
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        payload.update({k: v for k, v in extra_params.items() if v is not None})

        return self.openai_client.responses.stream(**payload)

    @staticmethod
    def _supports_sampling_params(model_name: str) -> bool:
        """Some reasoning models disallow temperature/top_p tweaks."""
        reasoning_prefixes = ("gpt-5", "gpt-5.", "gpt-4o", "o4", "o3")
        return not any(model_name.startswith(prefix) for prefix in reasoning_prefixes)

    @staticmethod
    def extract_response_text(response: Any) -> str:
        """Concatenate assistant text output from a Responses API call."""
        if not response:
            return ""
        text = getattr(response, "output_text", "") or ""
        return text.strip()

    @staticmethod
    def response_usage_to_metadata(usage: Any) -> Dict[str, Optional[int]]:
        """Convert Responses API usage to the legacy metadata shape."""
        if not usage:
            return {
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
            }

        return {
            "prompt_tokens": getattr(usage, "input_tokens", None),
            "completion_tokens": getattr(usage, "output_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    def get_initialization_status(self) -> Dict[str, Any]:
        """Get the current initialization status"""
        return {
            "status": self.initialization_status,
            "progress": self.initialization_progress,
            "message": self.initialization_message
        }
    
    def get_model_configuration(self) -> Dict[str, Any]:
        """Get current model configuration"""
        return {
            "current_provider": self.current_provider,
            "provider_name": self.available_providers[self.current_provider]["name"],
            "embedding_model": self.embedding_model,
            "chat_model": self.chat_model,
            "writing_model": self.writing_model,
            "available_providers": self.available_providers,
            "model_descriptions": {
                "gpt-5": "Most capable GPT model with latest reasoning upgrades",
                "gpt-5-mini": "Faster GPT-5 variant suitable for interactive chats",
                "gpt-4o-mini": "Fast GPT-4o variant ideal for streaming conversation",
                "gpt-4o-mini": "Fastest & cheapest GPT-4o model, great for most tasks",
                "gpt-4o": "Most capable GPT-4o model, best for complex reasoning",
                "gpt-4-turbo": "Fast GPT-4 with latest knowledge, good balance",
                "gpt-4": "Standard GPT-4, reliable and well-tested",
                "gpt-3.5-turbo": "Fast and cost-effective, good for simple tasks",
                "claude-3-5-sonnet": "Latest Claude model, excellent reasoning",
                "claude-3-5-haiku": "Fast Claude model, great for quick responses",
                "llama-3.1-8b": "Fast open-source model, good for basic tasks",
                "llama-3.1-70b": "High-quality open-source model",
                "gemini-1.5-pro": "Google's latest model, excellent performance",
                "gemini-1.5-flash": "Fast Google model, good balance"
            }
        }
    
    def update_model_configuration(self, provider: str, embedding_model: str = None, chat_model: str = None) -> bool:
        """Update model configuration"""
        try:
            if provider not in self.available_providers:
                logger.error(f"Provider {provider} not supported")
                return False
            
            self.current_provider = provider
            
            if embedding_model and embedding_model in self.available_providers[provider]["embedding_models"]:
                self.embedding_model = embedding_model
                logger.info(f"Updated embedding model to {embedding_model}")
            
            if chat_model and chat_model in self.available_providers[provider]["chat_models"]:
                self.chat_model = chat_model
                logger.info(f"Updated chat model to {chat_model}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating model configuration: {str(e)}")
            return False

    # Embedding generation removed - we now process full documents instead

    # def semantic_search(self, db: Session, query: str, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    #     """
    #     Perform semantic search across user's document chunks using OpenAI embeddings
    #     """
    #     # This method is disabled - we now use full document retrieval instead
    #     return []

    # def _calculate_cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
    #     """
    #     Calculate cosine similarity between two vectors
    #     """
    #     # This method is disabled - we now use full document retrieval instead
    #     return 0.0

    def generate_rag_response(self, query: str, documents: List[Dict[str, Any]]) -> str:
        """
        Generate RAG response using full document content instead of chunks
        """
        if not self.openai_client:
            return "AI service not available. Please try again later."
        
        try:
            # Prepare context from full documents
            context = ""
            for i, doc in enumerate(documents, 1):
                context += f"Document {i}: {doc['title']}\n"
                context += f"Content:\n{doc['content']}\n"
                context += f"---\n\n"
            
            # Create the prompt
            prompt = f"""You are an AI assistant helping a user understand their documents. Answer the user's question based on the provided document content.

            IMPORTANT: 
            - Be specific and direct in your answers
            - Use concrete details from the documents
            - Cite which document(s) contain the relevant information
            - If the documents contain the answer, provide it confidently
            - Don't be overly cautious or vague

            Question: {query}

            Available Documents:
            {context}

            Instructions:
            - Answer the question using specific information from the documents
            - Reference document titles when citing information
            - Be detailed and helpful
            - If you can't find relevant information, say so clearly

            Answer:"""
            
            # Generate response using OpenAI
            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are a knowledgeable research assistant. When users ask about their documents, provide specific, detailed answers based on the document content. Be confident and helpful."},
                    {"role": "user", "content": prompt}
                ],
                max_output_tokens=4000,
                temperature=0.7
            )
            
            answer = self.extract_response_text(response)
            
            # Add document information
            docs_info = "\n\nDocuments Used:\n"
            for i, doc in enumerate(documents, 1):
                # Use only the title/original filename, no encoded UUID filenames
                title = doc['title'] if doc['title'] else doc['filename']
                docs_info += f"{i}. {title}\n"
            
            return answer + docs_info
            
        except Exception as e:
            logger.error(f"Error generating RAG response: {str(e)}")
            return f"Error generating response: {str(e)}"

    def chat_with_documents(self, db: Session, user_id: str, query: str) -> Dict[str, Any]:
        """
        Main function to chat with documents using RAG
        """
        try:
            logger.info(f"Processing chat query: '{query}' for user {user_id}")
            
            # Check if we're in mock mode (no OpenAI API key)
            if not self.openai_client:
                logger.info("🤖 Mock mode: Providing mock AI response")
                mock_response = self._generate_mock_response(query)
                chat_id = f"mock-{int(time.time())}"
                
                return {
                    "response": mock_response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }
            
            # Get relevant documents (simpler approach)
            logger.info("🔍 Getting relevant documents...")
            documents = self.get_relevant_documents(db, query, user_id, limit=3)
            logger.info(f"🔍 Found {len(documents)} relevant documents")
            
            if not documents:
                logger.info("📝 No documents found, returning default response")
                response = "I couldn't find any documents in your library. Please upload some documents first."
                
                # Store chat session even when no documents found
                logger.info("💾 Storing chat session (no documents)...")
                chat_id = self._store_chat_session(db, user_id, query, response, [])
                logger.info(f"💾 Chat session stored with ID: {chat_id}")
                
                # Handle case where chat session storage failed
                if chat_id is None:
                    logger.warning(f"Failed to store chat session for user {user_id}, using temporary ID")
                    chat_id = f"no-docs-{int(time.time())}"
                
                return {
                    "response": response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }
            
            # Generate RAG response using full documents
            logger.info("🤖 Generating RAG response from full documents...")
            response = self.generate_rag_response(query, documents)
            logger.info(f"🤖 RAG response generated, length: {len(response)}")
            
            # Store chat session and get the ID
            logger.info("💾 Storing chat session...")
            chat_id = self._store_chat_session(db, user_id, query, response, documents)
            logger.info(f"💾 Chat session stored with ID: {chat_id}")
            
            # Handle case where chat session storage failed
            if chat_id is None:
                logger.warning(f"Failed to store chat session for user {user_id}, continuing without chat_id")
                chat_id = "temp-" + str(int(time.time()))  # Generate temporary ID
            
            result = {
                "response": response,
                "sources": documents,  # Return the document objects
                "sources_data": documents,
                "chat_id": chat_id
            }
            
            logger.info(f"✅ Returning result with chat_id: {chat_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error in chat_with_documents: {str(e)}")
            return {
                "response": f"An error occurred while processing your request: {str(e)}",
                "sources": [],
                "sources_data": [],
                "chat_id": f"error-{int(time.time())}"  # Always include chat_id
            }

    def _store_chat_session(self, db: Session, user_id: str, query: str, response: str, sources: List[Dict[str, Any]]) -> str:
        """
        Store chat session in database and return the chat ID
        """
        try:
            from app.models.ai_chat_session import AIChatSession
            
            chat_session = AIChatSession(
                user_id=user_id,
                query=query,
                response=response,
                sources=sources
            )
            
            db.add(chat_session)
            db.commit()
            logger.info(f"Stored chat session for user {user_id}")
            
            return str(chat_session.id)
            
        except Exception as e:
            logger.error(f"Error storing chat session: {str(e)}")
            db.rollback()
            return None

    def get_chat_history(self, db: Session, user_id: str, limit: int = 20) -> List[Any]:
        """
        Get user's AI chat history
        """
        try:
            from app.models.ai_chat_session import AIChatSession
            
            # Get chat sessions for the user, ordered by most recent first
            chat_sessions = db.query(AIChatSession).filter(
                AIChatSession.user_id == user_id
            ).order_by(
                AIChatSession.created_at.desc()
            ).limit(limit).all()
            
            logger.info(f"Retrieved {len(chat_sessions)} chat sessions for user {user_id}")
            return chat_sessions
            
        except Exception as e:
            logger.error(f"Error getting chat history for user {user_id}: {str(e)}")
            return []

    # ===== AI WRITING TOOLS METHODS =====

    def generate_text(self, text: str, instruction: str, context: Optional[str] = None, max_length: int = 500) -> Dict[str, Any]:
        """
        Generate, expand, rephrase, or complete text using AI
        """
        try:
            start_time = time.time()
            writing_model = self.writing_model
            logger.info(f"Generating text with instruction: {instruction} using model {writing_model}")
            
            # Check if OpenAI client is available
            if not self.openai_client:
                logger.warning("OpenAI client not available, using mock response")
                return self._generate_mock_text_response(text, instruction, context, max_length)
            
            # Build the prompt based on instruction
            if instruction.lower() == "expand":
                prompt = f"Please expand the following text, making it more detailed and comprehensive while maintaining the same tone and style. Add relevant examples, explanations, and context:\n\n{text}"
            elif instruction.lower() == "rephrase":
                prompt = f"Please rephrase the following text in a different way while keeping the same meaning and maintaining academic writing style:\n\n{text}"
            elif instruction.lower() == "complete":
                prompt = f"Please complete the following text, continuing the thought naturally and maintaining the same style and tone:\n\n{text}"
            elif instruction.lower() == "summarize":
                prompt = f"Please provide a concise summary of the following text, capturing the key points and main ideas:\n\n{text}"
            else:
                prompt = f"Please {instruction} the following text:\n\n{text}"
            
            if context:
                prompt += f"\n\nAdditional context: {context}"
            
            prompt += f"\n\nPlease ensure the response is no longer than {max_length} words and maintains academic writing standards."
            
            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are an expert academic writing assistant. Help researchers improve their writing by providing clear, well-structured, and academically appropriate text."},
                    {"role": "user", "content": prompt}
                ],
                model=writing_model,
                max_output_tokens=min(max_length * 2, 2000),  # Estimate tokens needed
                temperature=0.7
            )
            
            generated_text = self.extract_response_text(response)
            processing_time = time.time() - start_time
            
            logger.info(f"Text generation completed in {processing_time:.2f}s")
            
            return {
                'generated_text': generated_text,
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.error(f"Error in text generation: {str(e)}")
            # Fallback to mock response on error
            return self._generate_mock_text_response(text, instruction, context, max_length)

    def check_grammar_and_style(self, text: str, check_grammar: bool = True, check_style: bool = True, check_clarity: bool = True) -> Dict[str, Any]:
        """
        Check grammar, style, and clarity of text using AI
        """
        try:
            start_time = time.time()
            writing_model = self.writing_model
            logger.info(f"Performing grammar and style check using model {writing_model}")
            
            # Check if OpenAI client is available
            if not self.openai_client:
                logger.warning("OpenAI client not available, using mock response")
                return self._generate_mock_grammar_response(text, check_grammar, check_style, check_clarity)
            
            # Build the analysis prompt
            analysis_parts = []
            if check_grammar:
                analysis_parts.append("grammar and punctuation")
            if check_style:
                analysis_parts.append("writing style and tone")
            if check_clarity:
                analysis_parts.append("clarity and readability")
            
            analysis_type = ", ".join(analysis_parts)
            
            prompt = f"""Please analyze the following text for {analysis_type}. 
            
            Provide:
            1. A corrected version of the text
            2. Specific suggestions for improvement
            3. An overall quality score (0-100)
            
            Text to analyze:
            {text}
            
            Please format your response as:
            CORRECTED_TEXT: [corrected text here]
            SUGGESTIONS: [list of specific suggestions]
            SCORE: [0-100 score]"""
            
            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are an expert academic writing editor. Analyze text for grammar, style, and clarity, providing specific, actionable feedback."},
                    {"role": "user", "content": prompt}
                ],
                model=writing_model,
                max_output_tokens=1500,
                temperature=0.3
            )
            
            response_text = self.extract_response_text(response)
            processing_time = time.time() - start_time
            
            # Parse the response
            result = self._parse_grammar_response(response_text, text)
            result['processing_time'] = processing_time
            
            logger.info(f"Grammar check completed in {processing_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Error in grammar check: {str(e)}")
            # Fallback to mock response on error
            return self._generate_mock_grammar_response(text, check_grammar, check_style, check_clarity)

    def enhance_with_research_context(self, text: str, paper_ids: List[str], query_type: str, user_id: str) -> Dict[str, Any]:
        """
        Enhance text using research context from user's papers
        """
        try:
            start_time = time.time()
            writing_model = self.writing_model
            logger.info(f"Enhancing text with research context: {query_type} using model {writing_model}")
            
            # Check if OpenAI client is available
            if not self.openai_client:
                logger.warning("OpenAI client not available, using mock response")
                return self._generate_mock_research_response(text, query_type)
            
            # Get relevant research context from papers
            # This would integrate with the existing document processing system
            # For now, we'll provide a basic enhancement
            
            prompt = f"""Please enhance the following text using research best practices and academic standards.
            
            Enhancement type: {query_type}
            Text to enhance: {text}
            
            Please provide:
            1. An enhanced version of the text
            2. Specific suggestions for improvement
            3. Research-based recommendations
            
            Focus on making the text more academically rigorous, well-supported, and clear."""
            
            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are an expert research writing consultant. Help researchers improve their academic writing by providing research-based enhancements and suggestions."},
                    {"role": "user", "content": prompt}
                ],
                model=writing_model,
                max_output_tokens=1500,
                temperature=0.5
            )
            
            enhanced_text = self.extract_response_text(response)
            processing_time = time.time() - start_time
            
            logger.info(f"Research context enhancement completed in {processing_time:.2f}s")
            
            return {
                'enhanced_text': enhanced_text,
                'suggestions': [
                    "Text enhanced using AI research writing best practices",
                    "Consider adding more specific examples and citations",
                    "Review for clarity and academic tone"
                ],
                'relevant_sources': [],  # Would be populated with actual paper references
                'processing_time': processing_time
            }
            
        except Exception as e:
            logger.error(f"Error in research context enhancement: {str(e)}")
            # Fallback to mock response on error
            return self._generate_mock_research_response(text, query_type)

    def get_relevant_documents(self, db: Session, query: str, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Get relevant documents using simple keyword matching instead of complex embeddings
        """
        try:
            logger.info(f"🔍 Getting relevant documents for query: '{query}'")
            
            # Simple approach: get all processed documents and let the LLM decide relevance
            from app.models.document import Document
            
            documents = db.query(Document).filter(
                Document.owner_id == user_id,
                Document.is_processed_for_ai == True
            ).all()
            
            if not documents:
                logger.info("📝 No processed documents found")
                return []
            
            logger.info(f"📚 Found {len(documents)} processed documents")
            
            # Return document info for the LLM to process
            relevant_docs = []
            for doc in documents:
                # Get the document content (first few chunks for context)
                from app.models.document_chunk import DocumentChunk
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == doc.id
                ).order_by(DocumentChunk.chunk_index).limit(3).all()
                
                # Combine chunks into document content
                doc_content = "\n\n".join([chunk.chunk_text for chunk in chunks])
                
                # Use the most user-friendly name available
                display_name = doc.title or doc.original_filename
                
                relevant_docs.append({
                    'document_id': str(doc.id),
                    'title': display_name,
                    'content': doc_content,
                    'filename': display_name,  # Use display name instead of original_filename
                    'uploaded_at': doc.created_at.isoformat()
                })
            
            return relevant_docs[:limit]
            
        except Exception as e:
            logger.error(f"❌ Error getting relevant documents: {str(e)}")
            import traceback
            logger.error(f"❌ Full traceback: {traceback.format_exc()}")
            return []

    def _generate_mock_response(self, query: str) -> str:
        """
        Generate a mock AI response for testing purposes when no OpenAI API key is available
        """
        import random
        
        # Mock responses for common research-related queries
        mock_responses = [
            f"I understand you're asking about '{query}'. This is a mock response since the AI service is in demo mode. In a production environment, I would analyze your documents and provide a detailed, contextual answer based on your research library.",
            
            f"Great question about '{query}'! I'm currently running in demo mode, so I can't access your documents to provide a specific answer. However, I can help you with general research guidance once you configure an OpenAI API key.",
            
            f"Regarding '{query}', I'd love to help you with a detailed analysis of your research documents. Currently, I'm in demo mode and can't access your library. To get full AI assistance, please add your OpenAI API key to the environment configuration.",
            
            f"Interesting question about '{query}'! I'm designed to help researchers by analyzing their uploaded documents and providing insights. Right now, I'm in demo mode, but you can enable full AI functionality by configuring your OpenAI API key."
        ]
        
        # Add some context-specific responses
        if any(word in query.lower() for word in ['method', 'methodology', 'approach']):
            return f"For questions about methodology like '{query}', I would typically analyze your research documents to understand your specific approach and provide tailored advice. Currently in demo mode - add your OpenAI API key for full functionality."
        
        if any(word in query.lower() for word in ['result', 'finding', 'conclusion']):
            return f"Regarding your question about '{query}', I would examine your research results and findings to provide a comprehensive analysis. I'm currently in demo mode, but you can enable full AI analysis by configuring your OpenAI API key."
        
        if any(word in query.lower() for word in ['literature', 'review', 'background']):
            return f"Great question about '{query}'! I would analyze your literature review and background research to provide insights and identify gaps. Currently in demo mode - configure your OpenAI API key to unlock full AI-powered literature analysis."
        
        # Return a random mock response
        return random.choice(mock_responses)

    # ===== MOCK RESPONSE METHODS =====
    
    def _generate_mock_text_response(self, text: str, instruction: str, context: Optional[str] = None, max_length: int = 500) -> Dict[str, Any]:
        """Generate mock response when OpenAI client is not available"""
        logger.info("Generating mock text response")
        
        # Create realistic mock responses based on instruction
        if instruction.lower() == "expand":
            mock_text = f"{text} This expanded version provides additional context and examples to support the main points. The enhanced content maintains academic rigor while offering comprehensive coverage of the topic."
        elif instruction.lower() == "rephrase":
            mock_text = f"Here is a rephrased version of the original text: {text.replace('This', 'The following').replace('is', 'represents')}"
        elif instruction.lower() == "complete":
            mock_text = f"{text} This continuation builds upon the established foundation, providing additional insights and concluding thoughts that align with the academic tone and style of the preceding text."
        elif instruction.lower() == "summarize":
            mock_text = f"Summary: The text discusses key concepts and provides essential information on the topic, presenting a concise overview of the main points."
        else:
            mock_text = f"AI-enhanced version: {text} (Enhanced using {instruction} functionality)"
        
        return {
            'generated_text': mock_text,
            'processing_time': 0.1
        }

    def _generate_mock_grammar_response(self, text: str, check_grammar: bool, check_style: bool, check_clarity: bool) -> Dict[str, Any]:
        """Generate mock grammar check response when OpenAI client is not available"""
        logger.info("Generating mock grammar response")
        
        # Create realistic mock corrections
        corrected_text = text
        if check_grammar:
            corrected_text = corrected_text.replace("its", "it's")  # Simple example correction
        
        suggestions = []
        if check_grammar:
            suggestions.append("Consider reviewing punctuation usage")
        if check_style:
            suggestions.append("Maintain consistent academic tone throughout")
        if check_clarity:
            suggestions.append("Ensure each sentence conveys a single clear idea")
        
        return {
            'corrected_text': corrected_text,
            'original_text': text,
            'suggestions': suggestions,
            'overall_score': 85.0,
            'processing_time': 0.1
        }

    def _generate_mock_research_response(self, text: str, query_type: str) -> Dict[str, Any]:
        """Generate mock research enhancement response when OpenAI client is not available"""
        logger.info("Generating mock research response")
        
        enhanced_text = f"{text} [Enhanced with research context: This version incorporates academic best practices and research-based recommendations to strengthen the argument and improve clarity.]"
        
        return {
            'enhanced_text': enhanced_text,
            'original_text': text,
            'suggestions': [
                "Text enhanced using AI research writing best practices",
                "Consider adding more specific examples and citations",
                "Review for clarity and academic tone"
            ],
            'relevant_sources': [],
            'processing_time': 0.1
        }

    def _parse_grammar_response(self, response_text: str, original_text: str) -> Dict[str, Any]:
        """Parse the AI response for grammar check results"""
        try:
            corrected_text = original_text
            suggestions = []
            score = 85.0
            
            # Simple parsing logic - in production, you might want more sophisticated parsing
            lines = response_text.split('\n')
            for line in lines:
                if line.startswith('CORRECTED_TEXT:'):
                    corrected_text = line.replace('CORRECTED_TEXT:', '').strip()
                elif line.startswith('SUGGESTIONS:'):
                    # Extract suggestions
                    suggestion_text = line.replace('SUGGESTIONS:', '').strip()
                    if suggestion_text:
                        suggestions = [s.strip() for s in suggestion_text.split(',')]
                elif line.startswith('SCORE:'):
                    try:
                        score_text = line.replace('SCORE:', '').strip()
                        score = float(score_text)
                    except ValueError:
                        score = 85.0
            
            return {
                'corrected_text': corrected_text,
                'original_text': original_text,
                'suggestions': suggestions,
                'overall_score': score
            }
            
        except Exception as e:
            logger.error(f"Error parsing grammar response: {str(e)}")
            # Fallback to basic response
            return {
                'corrected_text': original_text,
                'original_text': original_text,
                'suggestions': ["Error parsing AI response. Please try again."],
                'overall_score': 85.0
            }

    # ===== REFERENCE-BASED RAG METHODS =====

    def chat_with_references(
        self, 
        db: Session, 
        user_id: str, 
        query: str, 
        paper_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Chat with references using RAG (paper-scoped or global library)
        
        Args:
            db: Database session
            user_id: User ID
            query: User's question
            paper_id: If provided, scope to this paper's references; otherwise use global library
            
        Returns:
            Dict with response, sources, and chat_id
        """
        try:
            logger.info(f"Processing reference chat query: '{query}' for user {user_id}")
            
            if paper_id:
                logger.info(f"Scoped to paper: {paper_id}")
            else:
                logger.info("Scoped to global library")

            # Handle simple greetings without invoking RAG
            if self._is_greeting(query):
                friendly = "Hi there! Ask me about this paper's references and I'll help summarize or answer questions."
                chat_id = f"greet-{int(time.time())}"
                return {
                    "response": friendly,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id,
                }
            
            # Intent: simple listing (avoid LLM + retrieval)
            intent = self._detect_listing_intent(query)
            if intent:
                logger.info(f"🧭 Listing intent detected: {intent}")
                response, sources = self._handle_listing_intent(db, user_id, intent, paper_id)
                chat_id = self._store_reference_chat_session(db, user_id, query, response, sources, paper_id) or f"list-{int(time.time())}"
                return {
                    "response": response,
                    "sources": [s["title"] for s in sources],
                    "sources_data": sources,
                    "chat_id": chat_id,
                }

            # Check if we're in mock mode (no OpenAI API key)
            if not self.openai_client:
                logger.info("🤖 Mock mode: Providing mock AI response")
                mock_response = self._generate_mock_reference_response(query, paper_id)
                chat_id = f"mock-ref-{int(time.time())}"
                
                return {
                    "response": mock_response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }
            
            # Get relevant reference chunks
            logger.info("🔍 Getting relevant reference chunks...")
            chunks = self.get_relevant_reference_chunks(db, query, user_id, paper_id, limit=8)
            logger.info(f"🔍 Found {len(chunks)} relevant chunks")
            
            if not chunks:
                logger.info("📝 No relevant reference chunks found, returning default response")
                scope_msg = f"for paper '{paper_id}'" if paper_id else "in your library"
                response = (
                    f"I couldn't find relevant content for your query {scope_msg}. "
                    f"Try a more specific question, or ensure your references (with PDFs) are processed."
                )
                
                # Store chat session
                chat_id = self._store_reference_chat_session(db, user_id, query, response, [], paper_id)
                
                if chat_id is None:
                    chat_id = f"no-refs-{int(time.time())}"
                
                return {
                    "response": response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }
            
            # Generate RAG response using reference chunks
            logger.info("🤖 Generating RAG response from reference chunks...")
            response = self.generate_reference_rag_response(query, chunks)
            logger.info(f"🤖 Reference RAG response generated, length: {len(response)}")
            
            # Prepare source information
            sources = self._prepare_reference_sources(chunks)
            
            # Store chat session
            logger.info("💾 Storing reference chat session...")
            chat_id = self._store_reference_chat_session(db, user_id, query, response, sources, paper_id)
            logger.info(f"💾 Reference chat session stored with ID: {chat_id}")
            
            if chat_id is None:
                chat_id = f"ref-chat-{int(time.time())}"
            
            return {
                "response": response,
                "sources": [s["title"] for s in sources],
                "sources_data": sources,
                "chat_id": chat_id
            }
            
        except Exception as e:
            logger.error(f"Error in reference chat: {str(e)}")
        return {
            "response": f"Error processing your request: {str(e)}",
            "sources": [],
            "sources_data": [],
            "chat_id": f"error-{int(time.time())}"
        }

    @staticmethod
    def _is_greeting(text: str) -> bool:
        """Detect short greeting/pleasantry to avoid unnecessary RAG calls."""
        if not text:
            return False
        q = text.strip().lower()
        if len(q) > 24:
            return False
        greetings = {
            "hi", "hey", "hello", "hello there", "hi there", "hey there", "hiya", "howdy",
            "good morning", "good afternoon", "good evening", "yo"
        }
        return q in greetings

    def _detect_listing_intent(self, query: str) -> Optional[str]:
        """Detect simple listing/summary intents to bypass RAG.
        Returns one of: 'references', 'papers', or None.
        """
        try:
            q = (query or "").strip().lower()
            if not q:
                return None
            # Ignore auto-added context from clients
            if "attached references:" in q:
                return None
            # Common phrasings
            markers_refs = ["references", "citations", "sources", "refs"]
            markers_papers = ["papers", "paper list", "my papers", "projects"]
            # Imperative/listing clues
            list_verbs = ["what", "which", "list", "show", "how many", "count"]
            if any(v in q for v in list_verbs):
                if any(m in q for m in markers_refs):
                    return "references"
                if any(m in q for m in markers_papers) or "what paper" in q or "what papers" in q:
                    return "papers"
            # Very broad questions like "what paper you do have" (typo-friendly)
            if "what paper" in q:
                return "papers"
        except Exception:
            pass
        return None

    def _handle_listing_intent(self, db: Session, user_id: str, intent: str, paper_id: Optional[str]) -> (str, List[Dict[str, Any]]):
        """Build a deterministic response for listing intents.
        Returns (response_text, sources_data)
        """
        from app.models.reference import Reference
        from app.models.research_paper import ResearchPaper
        from app.models.paper_reference import PaperReference
        import uuid as _uuid
        try:
            user_uuid = user_id if not isinstance(user_id, str) else _uuid.UUID(user_id)
        except Exception:
            user_uuid = user_id

        if intent == "references":
            # If paper scoped, list that paper's references; otherwise, user's library
            if paper_id:
                refs = (
                    db.query(Reference)
                    .join(PaperReference, PaperReference.reference_id == Reference.id)
                    .filter(PaperReference.paper_id == paper_id)
                    .order_by(Reference.created_at.desc())
                    .all()
                )
                title = db.query(ResearchPaper.title).filter(ResearchPaper.id == paper_id).scalar() or "this paper"
                if not refs:
                    return (f"This paper has 0 references.", [] )
                lines = []
                sources = []
                for i, r in enumerate(refs, 1):
                    lines.append(f"{i}. {r.title} ({r.year or 'n/a'}) — status: {r.status}")
                    sources.append({"id": str(r.id), "title": r.title, "status": r.status})
                resp = f"This paper ('{title}') has {len(refs)} references:\n" + "\n".join(lines)
                return (resp, sources)
            else:
                refs = db.query(Reference).filter(Reference.owner_id == user_uuid).order_by(Reference.created_at.desc()).limit(50).all()
                if not refs:
                    return ("You have 0 references in your library.", [])
                lines = []
                sources = []
                for i, r in enumerate(refs, 1):
                    lines.append(f"{i}. {r.title} ({r.year or 'n/a'}) — paper: {str(r.paper_id)[:8] if r.paper_id else 'none'}")
                    sources.append({"id": str(r.id), "title": r.title, "paper_id": str(r.paper_id) if r.paper_id else None})
                resp = f"You have {len(refs)} references in your library (showing up to 50):\n" + "\n".join(lines)
                return (resp, sources)

        if intent == "papers":
            # List user's papers
            papers = db.query(ResearchPaper).filter(ResearchPaper.owner_id == user_uuid).order_by(ResearchPaper.created_at.desc()).limit(50).all()
            if not papers:
                return ("You have 0 papers.", [])
            lines = []
            sources = []
            for i, p in enumerate(papers, 1):
                lines.append(f"{i}. {p.title} — id: {p.id}")
                sources.append({"id": str(p.id), "title": p.title})
            resp = f"You have {len(papers)} papers (showing up to 50):\n" + "\n".join(lines)
            return (resp, sources)

        # Fallback
        return ("I can list your papers or references if you specify.", [])

    def get_relevant_reference_chunks(
        self,
        db: Session,
        query: str,
        user_id: str,
        paper_id: Optional[str] = None,
        limit: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Get relevant chunks from references based on scope
        """
        from app.models.document_chunk import DocumentChunk
        from app.models.reference import Reference
        from app.models.paper_reference import PaperReference
        
        try:
            import math as _math
            import json as _json
            import uuid as _uuid
            # Debug logging for the query parameter
            logger.info(f"🔍 get_relevant_reference_chunks called with query type: {type(query)}, value: {repr(query)}")
            
            # Ensure query is a string
            if not isinstance(query, str):
                logger.error(f"❌ Query parameter is not a string! Type: {type(query)}, Value: {repr(query)}")
                if hasattr(query, '__iter__') and not isinstance(query, str):
                    # If it's a list/iterable, join it
                    query = ' '.join(str(item) for item in query)
                    logger.info(f"🔧 Converted query to string: {repr(query)}")
                else:
                    query = str(query)
                    logger.info(f"🔧 Converted query to string: {repr(query)}")
            
            # Normalize user_id to UUID for reliable filtering
            try:
                user_uuid = user_id if not isinstance(user_id, str) else _uuid.UUID(user_id)
            except Exception:
                # If conversion fails, keep original (DB may coerce), but log
                logger.warning(f"Could not parse user_id as UUID: {user_id}")
                user_uuid = user_id

            # Base query for chunks with reference_id
            query_base = db.query(DocumentChunk, Reference).join(
                Reference, DocumentChunk.reference_id == Reference.id
            ).filter(
                Reference.status == 'analyzed',
                DocumentChunk.reference_id.isnot(None)
            )
            
            # Scope to paper if provided
            if paper_id:
                # When scoped to a paper, don't restrict by owner (paper access already validated)
                query_base = query_base.join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(PaperReference.paper_id == paper_id)
            else:
                # Global scope: restrict to the user's own reference library
                query_base = query_base.filter(Reference.owner_id == user_uuid)
            
            # Get all chunks in scope
            chunk_results = query_base.all()
            if not chunk_results:
                return []

            # Prefer embedding-based scoring if OpenAI client available and any embeddings exist
            used_embedding = False
            scored_chunks: List[Dict[str, Any]] = []
            if self.openai_client:
                try:
                    qemb = self.openai_client.embeddings.create(
                        model=self.embedding_model,
                        input=query
                    ).data[0].embedding

                    def _cos(a, b):
                        try:
                            sa = sum(x*y for x, y in zip(a, b))
                            na = _math.sqrt(sum(x*x for x in a))
                            nb = _math.sqrt(sum(y*y for y in b))
                            return (sa / (na * nb)) if na and nb else 0.0
                        except Exception:
                            return 0.0

                    have_any_emb = False
                    for chunk, reference in chunk_results:
                        emb = getattr(chunk, 'embedding', None)
                        if emb is None:
                            continue
                        # Some drivers may return JSON-encoded embeddings
                        if isinstance(emb, str):
                            try:
                                emb = _json.loads(emb)
                            except Exception:
                                emb = None
                        if not emb:
                            continue
                        have_any_emb = True
                        score = float(_cos(qemb, emb))
                        if score > 0:
                            scored_chunks.append({'chunk': chunk, 'reference': reference, 'score': score})
                    if have_any_emb:
                        used_embedding = True
                except Exception as e:
                    logger.warning(f"Embedding-based retrieval failed, falling back to keywords: {e}")

            if not scored_chunks:
                # Keyword-based relevance scoring
                query_terms = [term.lower() for term in query.split() if len(term) > 2]
                for chunk, reference in chunk_results:
                    text = (chunk.chunk_text or '').lower()
                    score = sum(text.count(term) for term in query_terms)
                    # Boost score for title and abstract matches
                    if reference.title:
                        title_text = reference.title.lower()
                        score += 2 * sum(title_text.count(term) for term in query_terms)
                    if reference.abstract:
                        abstract_text = reference.abstract.lower()
                        score += 1.5 * sum(abstract_text.count(term) for term in query_terms)
                    if score > 0:
                        scored_chunks.append({'chunk': chunk, 'reference': reference, 'score': float(score)})

            # If still nothing matched, provide a sensible fallback: first chunk per reference
            if not scored_chunks:
                logger.info("No matches from embeddings/keywords; falling back to first chunk per reference")
                # Keep one chunk per reference, preserving order
                seen_refs = set()
                for chunk, reference in chunk_results:
                    if reference.id in seen_refs:
                        continue
                    seen_refs.add(reference.id)
                    scored_chunks.append({'chunk': chunk, 'reference': reference, 'score': 0.0})

            # Sort and limit
            scored_chunks.sort(key=lambda x: x['score'], reverse=True)
            top_items = scored_chunks[:max(1, min(limit, 20))]

            # Convert to expected format
            results: List[Dict[str, Any]] = []
            for item in top_items:
                chunk = item['chunk']
                reference = item['reference']
                results.append({
                    'text': chunk.chunk_text,
                    'chunk_index': chunk.chunk_index,
                    'reference_id': str(reference.id),
                    'reference_title': reference.title,
                    'reference_authors': reference.authors,
                    'reference_year': reference.year,
                    'reference_journal': reference.journal,
                    'relevance_score': item['score'],
                    'metadata': chunk.chunk_metadata or {},
                })

            return results
            
        except Exception as e:
            logger.error(f"Error getting relevant reference chunks: {str(e)}")
            return []

    def generate_reference_rag_response(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        """Generate RAG response using reference chunks (non-streaming)."""
        if not self.openai_client:
            return "AI service not available. Please try again later."

        try:
            prompt, references_used = self._build_reference_prompt(query, chunks)

            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are a knowledgeable research assistant specializing in academic literature. Provide specific, well-cited answers in plain text (no Markdown, no bullet lists). Cite references using (Reference Title, Year)."},
                    {"role": "user", "content": prompt}
                ],
                max_output_tokens=4000,
                temperature=0.7
            )

            answer = self.extract_response_text(response)

            refs_info = "\n\nReferences Used:\n"
            for ref_id, ref_data in references_used.items():
                title = ref_data['title']
                authors = ref_data.get('authors', [])
                year = ref_data.get('year')
                journal = ref_data.get('journal')

                ref_citation = f"• {title}"
                if authors:
                    authors_str = ", ".join(authors[:3])  # First 3 authors
                    if len(authors) > 3:
                        authors_str += " et al."
                    ref_citation += f" - {authors_str}"
                if year:
                    ref_citation += f" ({year})"
                if journal:
                    ref_citation += f" - {journal}"

                refs_info += ref_citation + "\n"

            return answer + refs_info

        except Exception as e:
            logger.error(f"Error generating reference RAG response: {str(e)}")
            return f"Error generating response: {str(e)}"

    def stream_reference_rag_response(self, query: str, chunks: List[Dict[str, Any]]):
        """Stream RAG response using reference chunks."""
        if not self.openai_client:
            yield "AI service not available. Please try again later."
            return

        try:
            prompt, _ = self._build_reference_prompt(query, chunks)
            messages = [
                {
                    "role": "system",
                    "content": "You are a knowledgeable research assistant specializing in academic literature. Provide specific, well-cited answers in plain text (no Markdown, no bullet lists). Cite references using (Reference Title, Year)."
                },
                {"role": "user", "content": prompt},
            ]
            yield from self._stream_chat(
                messages=messages,
                model=self.chat_model,
                temperature=0.7,
                max_output_tokens=4000,
            )
        except Exception as e:
            logger.error(f"Error streaming reference response: {str(e)}")
            yield f"[error streaming response: {str(e)}]"

    def _build_reference_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
        """Build prompt and metadata for reference-based RAG."""
        context = ""
        references_used: Dict[str, Any] = {}

        for i, chunk in enumerate(chunks, 1):
            ref_id = chunk['reference_id']
            ref_title = chunk['reference_title'] or f"Reference {ref_id}"

            if ref_id not in references_used:
                references_used[ref_id] = {
                    'title': ref_title,
                    'authors': chunk.get('reference_authors', []),
                    'year': chunk.get('reference_year'),
                    'journal': chunk.get('reference_journal')
                }

            context += f"Chunk {i} (from '{ref_title}'):\n"
            context += f"{chunk['text']}\n"
            context += f"---\n\n"

        prompt = f"""You are an AI research assistant helping a user understand their reference library. Answer the user's question based on the provided text chunks from academic references.

IMPORTANT: 
- Be specific and cite the references that contain relevant information
- Use concrete details from the reference chunks
- When citing, use format: (Reference Title, Year) or (Author et al., Year)
- If multiple references support a point, cite all relevant ones
- Provide comprehensive answers that synthesize information across references
- If you can't find relevant information, say so clearly

Question: {query}

Available Reference Chunks:
{context}

Instructions:
- Answer the question using specific information from the reference chunks
- Cite references properly when using information
- Synthesize information from multiple sources when relevant
- Be detailed and provide academic-quality responses
- If conflicting information exists, acknowledge and explain the differences

Answer:"""
        return prompt, references_used

    def _generate_mock_reference_response(self, query: str, paper_id: Optional[str] = None) -> str:
        """Generate mock response for reference-based chat"""
        scope = f"in the paper's references" if paper_id else "in your reference library"
        return f"This is a mock AI response about '{query}' based on the content {scope}. The AI service is currently running in demonstration mode. Real responses would analyze your uploaded reference PDFs and provide insights based on the academic literature in your library."

    def _prepare_reference_sources(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare source information from reference chunks"""
        sources = {}
        
        for chunk in chunks:
            ref_id = chunk['reference_id']
            if ref_id not in sources:
                sources[ref_id] = {
                    'id': ref_id,
                    'title': chunk['reference_title'] or f"Reference {ref_id}",
                    'authors': chunk.get('reference_authors', []),
                    'year': chunk.get('reference_year'),
                    'journal': chunk.get('reference_journal'),
                    'chunk_count': 1
                }
            else:
                sources[ref_id]['chunk_count'] += 1
        
        return list(sources.values())

    def stream_generate_text(self, text: str, instruction: str, context: Optional[str] = None, max_length: int = 500):
        """Stream generate/expand/rephrase text using AI."""
        if not self.openai_client:
            yield self._generate_mock_text_response(text, instruction, context, max_length)['generated_text']
            return

        if instruction.lower() == "expand":
            prompt = f"Please expand the following text, making it more detailed and comprehensive while maintaining the same tone and style. Add relevant examples, explanations, and context:\n\n{text}"
        elif instruction.lower() == "rephrase":
            prompt = f"Please rephrase the following text in a different way while keeping the same meaning and maintaining academic writing style:\n\n{text}"
        elif instruction.lower() == "complete":
            prompt = f"Please complete the following text, continuing the thought naturally and maintaining the same style and tone:\n\n{text}"
        elif instruction.lower() == "summarize":
            prompt = f"Please provide a concise summary of the following text, capturing the key points and main ideas:\n\n{text}"
        else:
            prompt = f"Please {instruction} the following text:\n\n{text}"

        if context:
            prompt += f"\n\nAdditional context: {context}"

        prompt += f"\n\nPlease ensure the response is no longer than {max_length} words and maintains academic writing standards."

        try:
            messages = [
                {"role": "system", "content": "You are an expert academic writing assistant. Respond in plain text (no Markdown, no bullet lists). Provide clear, well-structured, and academically appropriate text."},
                {"role": "user", "content": prompt},
            ]
            yield from self._stream_chat(
                messages=messages,
                model=self.writing_model,
                temperature=0.7,
                max_output_tokens=min(max_length * 2, 2000),
            )
        except Exception as e:
            logger.error(f"Error streaming text generation: {str(e)}")
            yield f"[error streaming response: {str(e)}]"

    def _stream_chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        **extra_params: Any,
    ):
        """
        Helper to stream tokens from OpenAI chat completions API.
        """
        if not self.openai_client:
            yield ""
            return
        try:
            stream = self.openai_client.chat.completions.create(
                model=model or self.chat_model,
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_output_tokens,
                **extra_params,
            )
            for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = choices[0].delta
                part = ""
                # delta.content may be a list of text fragments
                if delta and getattr(delta, "content", None):
                    # content can be list of objects with .text attribute or plain strings
                    try:
                        part = "".join(
                            [c.text if hasattr(c, "text") else str(c) for c in delta.content]
                        )
                    except Exception:
                        part = "".join([str(c) for c in delta.content])
                if part:
                    yield part
        except Exception as e:
            logger.error(f"Error in _stream_chat: {str(e)}")
            yield f"[error streaming response: {str(e)}]"

    def _store_reference_chat_session(
        self,
        db: Session,
        user_id: str,
        query: str,
        response: str,
        sources: List[Dict[str, Any]],
        paper_id: Optional[str] = None
    ) -> Optional[str]:
        """Store reference-based chat session in database"""
        try:
            # This would create a new chat session table or extend existing one
            # For now, we'll use the existing chat session storage as a fallback
            return self._store_chat_session(db, user_id, query, response, sources)
            
        except Exception as e:
            logger.error(f"Error storing reference chat session: {str(e)}")
            return None
