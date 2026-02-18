import logging
import os
import re
from typing import List, Dict, Any, Optional

import openai

logger = logging.getLogger(__name__)


class AIClient:
    def __init__(self):
        self.openai_client = None
        self.initialization_status = "initializing"
        self.initialization_progress = 0
        self.initialization_message = "Setting up OpenAI API..."

        self.embedding_model = "text-embedding-3-small"
        self.chat_model = "gpt-5-mini"
        self.writing_model = "gpt-5-mini"

        self.current_provider = "openai"

        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key or "your-openai-api-key-here" in api_key or api_key.startswith("sk-your_"):
                self.initialization_status = "ready"
                self.initialization_progress = 100
                self.initialization_message = "AI Service Ready (No OpenAI API Key)"
                logger.info("AI Service initialized without API key")
                return

            logger.info(f"API Key loaded: {api_key[:20]}...")

            self.openai_client = openai.OpenAI(api_key=api_key)
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
        try:
            self.create_response(
                messages=[{"role": "user", "content": "Hello"}],
                max_output_tokens=32,
            )
            logger.info("OpenAI API connection test successful")
        except Exception as e:
            raise Exception(f"OpenAI API connection test failed: {str(e)}")

    def _require_client(self):
        if not self.openai_client:
            raise ValueError("OpenAI client is not configured")

    def format_messages_for_responses(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")
            normalized.append({"role": role, "content": content})
        return normalized

    def create_response(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        **extra_params: Any,
    ):
        self._require_client()

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "input": self.format_messages_for_responses(messages),
        }
        target_model = payload["model"]

        if temperature is not None and self._supports_sampling_params(target_model):
            payload["temperature"] = temperature
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        if reasoning_effort is not None and target_model.startswith("gpt-5"):
            payload["reasoning"] = {"effort": reasoning_effort}
        payload.update({k: v for k, v in extra_params.items() if v is not None})

        return self.openai_client.responses.create(**payload)

    def stream_response(
        self,
        *,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        reasoning_effort: Optional[str] = None,
        **extra_params: Any,
    ):
        self._require_client()

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "input": self.format_messages_for_responses(messages),
        }
        target_model = payload["model"]
        if temperature is not None and self._supports_sampling_params(target_model):
            payload["temperature"] = temperature
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens
        if reasoning_effort is not None and target_model.startswith("gpt-5"):
            payload["reasoning"] = {"effort": reasoning_effort}
        payload.update({k: v for k, v in extra_params.items() if v is not None})

        return self.openai_client.responses.stream(**payload)

    @staticmethod
    def _supports_sampling_params(model_name: str) -> bool:
        if "mini" in model_name:
            return True
        reasoning_prefixes = ("gpt-5", "gpt-6", "gpt-7")
        return not any(model_name.startswith(prefix) for prefix in reasoning_prefixes)

    @staticmethod
    def extract_response_text(response: Any) -> str:
        if not response:
            return ""
        text = getattr(response, "output_text", "") or ""
        return text.strip()

    @staticmethod
    def response_usage_to_metadata(usage: Any) -> Dict[str, Optional[int]]:
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
        return {
            "status": self.initialization_status,
            "progress": self.initialization_progress,
            "message": self.initialization_message
        }

    def get_model_configuration(self) -> Dict[str, Any]:
        return {
            "current_provider": self.current_provider,
            "embedding_model": self.embedding_model,
            "chat_model": self.chat_model,
            "writing_model": self.writing_model,
        }

    def update_model_configuration(self, provider: str, embedding_model: Optional[str] = None, chat_model: Optional[str] = None) -> bool:
        try:
            self.current_provider = provider
            if embedding_model:
                self.embedding_model = embedding_model
                logger.info(f"Updated embedding model to {embedding_model}")
            if chat_model:
                self.chat_model = chat_model
                logger.info(f"Updated chat model to {chat_model}")
            return True
        except Exception as e:
            logger.error(f"Error updating model configuration: {str(e)}")
            return False

    def _stream_chat(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        **extra_params: Any,
    ):
        if not self.openai_client:
            yield ""
            return
        try:
            target_model = model or self.chat_model

            if target_model.startswith("gpt-5"):
                with self.stream_response(
                    messages=messages,
                    model=target_model,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    **extra_params,
                ) as stream:
                    for event in stream:
                        if hasattr(event, 'type'):
                            if event.type == 'response.output_text.delta':
                                delta = getattr(event, 'delta', '')
                                if delta:
                                    yield self._strip_markdown_inline(delta)
                            elif event.type == 'response.content_part.delta':
                                delta = getattr(event, 'delta', None)
                                if delta and hasattr(delta, 'text'):
                                    yield self._strip_markdown_inline(delta.text)
                        elif hasattr(event, 'text'):
                            yield self._strip_markdown_inline(event.text)
                return

            params: Dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "stream": True,
            }
            if temperature is not None:
                params["temperature"] = temperature
            if max_output_tokens is not None:
                params["max_completion_tokens"] = max_output_tokens
            params.update({k: v for k, v in extra_params.items() if v is not None})

            stream = self.openai_client.chat.completions.create(**params)
            for chunk in stream:
                choices = getattr(chunk, "choices", None)
                if not choices:
                    continue
                delta = choices[0].delta
                part = ""
                if delta and getattr(delta, "content", None):
                    try:
                        part = "".join(
                            [c.text if hasattr(c, "text") else str(c) for c in delta.content]
                        )
                    except Exception:
                        part = "".join([str(c) for c in delta.content])
                if part:
                    yield self._strip_markdown_inline(part)
        except Exception as e:
            logger.error(f"Error in _stream_chat: {str(e)}")
            yield f"[error streaming response: {str(e)}]"

    @staticmethod
    def _strip_markdown_inline(text: str) -> str:
        if not text:
            return text
        cleaned = text
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"\*(.*?)\*", r"\1", cleaned)
        cleaned = cleaned.replace("###", "").replace("##", "").replace("#", "")
        return cleaned
