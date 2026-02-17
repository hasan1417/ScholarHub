import logging
import time
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

from app.services.ai_client import AIClient
from app.services.writing_tools_service import WritingToolsMixin
from app.services.reference_chat_service import ReferenceChatMixin

logger = logging.getLogger(__name__)


class AIService(AIClient, WritingToolsMixin, ReferenceChatMixin):

    def generate_rag_response(self, query: str, documents: List[Dict[str, Any]]) -> str:
        if not self.openai_client:
            raise ValueError("OpenAI client is not configured - cannot generate RAG response")

        try:
            context = ""
            for i, doc in enumerate(documents, 1):
                context += f"Document {i}: {doc['title']}\n"
                context += f"Content:\n{doc['content']}\n"
                context += f"---\n\n"

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

            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are a knowledgeable research assistant. When users ask about their documents, provide specific, detailed answers based on the document content. Be confident and helpful."},
                    {"role": "user", "content": prompt}
                ],
                max_output_tokens=4000,
                temperature=0.7
            )

            answer = self.extract_response_text(response)

            docs_info = "\n\nDocuments Used:\n"
            for i, doc in enumerate(documents, 1):
                title = doc['title'] if doc['title'] else doc['filename']
                docs_info += f"{i}. {title}\n"

            return answer + docs_info

        except Exception as e:
            logger.error(f"Error generating RAG response: {str(e)}")
            return f"Error generating response: {str(e)}"

    def chat_with_documents(self, db: Session, user_id: str, query: str) -> Dict[str, Any]:
        try:
            logger.info(f"Processing chat query: '{query}' for user {user_id}")

            if not self.openai_client:
                raise ValueError("OpenAI client is not configured - cannot chat with documents")

            logger.info("Getting relevant documents...")
            documents = self.get_relevant_documents(db, query, user_id, limit=3)
            logger.info(f"Found {len(documents)} relevant documents")

            if not documents:
                response = "I couldn't find any documents in your library. Please upload some documents first."
                chat_id = self._store_chat_session(db, user_id, query, response, [])
                if chat_id is None:
                    chat_id = f"no-docs-{int(time.time())}"
                return {
                    "response": response,
                    "sources": [],
                    "sources_data": [],
                    "chat_id": chat_id
                }

            logger.info("Generating RAG response from full documents...")
            response = self.generate_rag_response(query, documents)

            chat_id = self._store_chat_session(db, user_id, query, response, documents)
            if chat_id is None:
                chat_id = "temp-" + str(int(time.time()))

            result = {
                "response": response,
                "sources": documents,
                "sources_data": documents,
                "chat_id": chat_id
            }

            return result

        except Exception as e:
            logger.error(f"Error in chat_with_documents: {str(e)}")
            return {
                "response": f"An error occurred while processing your request: {str(e)}",
                "sources": [],
                "sources_data": [],
                "chat_id": f"error-{int(time.time())}"
            }

    def _store_chat_session(self, db: Session, user_id: str, query: str, response: str, sources: List[Dict[str, Any]]) -> str:
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
        try:
            from app.models.ai_chat_session import AIChatSession

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

    def get_relevant_documents(self, db: Session, query: str, user_id: str, limit: int = 3) -> List[Dict[str, Any]]:
        try:
            from app.models.document import Document
            from app.models.document_chunk import DocumentChunk

            documents = db.query(Document).filter(
                Document.owner_id == user_id,
                Document.is_processed_for_ai == True
            ).all()

            if not documents:
                return []

            relevant_docs = []
            for doc in documents:
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == doc.id
                ).order_by(DocumentChunk.chunk_index).limit(3).all()

                doc_content = "\n\n".join([chunk.chunk_text for chunk in chunks])

                display_name = doc.title or doc.original_filename

                relevant_docs.append({
                    'document_id': str(doc.id),
                    'title': display_name,
                    'content': doc_content,
                    'filename': display_name,
                    'uploaded_at': doc.created_at.isoformat()
                })

            return relevant_docs[:limit]

        except Exception as e:
            logger.error(f"Error getting relevant documents: {str(e)}")
            return []
