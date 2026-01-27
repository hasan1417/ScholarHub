"""
OpenRouter-Based Discussion AI Orchestrator

Uses OpenRouter API to support multiple AI models (GPT, Claude, Gemini, etc.)
Inherits from ToolOrchestrator and only overrides the AI calling methods.

Key difference from base ToolOrchestrator:
- Streams ONLY the final response (hides intermediate "thinking" during tool calls)
- Shows status messages during tool execution
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, List, Optional, TYPE_CHECKING

import openai

from app.core.config import settings
from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator, DISCUSSION_TOOLS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# Available OpenRouter models with pricing info
OPENROUTER_MODELS = {
    # OpenAI
    "openai/gpt-5.2": {"name": "GPT-5.2", "provider": "OpenAI"},
    "openai/gpt-5.2-pro": {"name": "GPT-5.2 Pro", "provider": "OpenAI"},
    "openai/gpt-4o": {"name": "GPT-4o", "provider": "OpenAI"},
    "openai/gpt-4o-mini": {"name": "GPT-4o Mini", "provider": "OpenAI"},
    # Anthropic
    "anthropic/claude-opus-4.5": {"name": "Claude Opus 4.5", "provider": "Anthropic"},
    "anthropic/claude-sonnet-4": {"name": "Claude Sonnet 4", "provider": "Anthropic"},
    "anthropic/claude-3.5-sonnet": {"name": "Claude 3.5 Sonnet", "provider": "Anthropic"},
    # Google
    "google/gemini-3-flash": {"name": "Gemini 3 Flash", "provider": "Google"},
    "google/gemini-2.0-flash-exp:free": {"name": "Gemini 2.0 Flash (Free)", "provider": "Google"},
    # DeepSeek
    "deepseek/deepseek-chat": {"name": "DeepSeek V3", "provider": "DeepSeek"},
    "deepseek/deepseek-r1": {"name": "DeepSeek R1", "provider": "DeepSeek"},
    # Meta
    "meta-llama/llama-3.3-70b-instruct": {"name": "Llama 3.3 70B", "provider": "Meta"},
    # Qwen
    "qwen/qwen-2.5-72b-instruct": {"name": "Qwen 2.5 72B", "provider": "Qwen"},
}


class OpenRouterOrchestrator(ToolOrchestrator):
    """
    AI orchestrator that uses OpenRouter for multi-model support.

    Inherits all tool implementations from ToolOrchestrator,
    only overrides the AI calling methods to use OpenRouter.
    """

    def __init__(self, ai_service: "AIService", db: "Session", model: str = "openai/gpt-5.2"):
        super().__init__(ai_service, db)
        self._model = model

        # Initialize OpenRouter client (OpenAI-compatible API)
        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            logger.warning("OPENROUTER_API_KEY not configured")

        self.openrouter_client = openai.OpenAI(
            api_key=api_key or "missing-key",
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            }
        ) if api_key else None

    @property
    def model(self) -> str:
        """Get the current model being used."""
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        """Set the model to use."""
        self._model = value

    def _call_ai_with_tools(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call OpenRouter with tool definitions (non-streaming)."""
        try:
            if not self.openrouter_client:
                return {
                    "content": "OpenRouter API not configured. Please check your OPENROUTER_API_KEY.",
                    "tool_calls": []
                }

            logger.info(f"Calling OpenRouter with model: {self.model}")

            response = self.openrouter_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=DISCUSSION_TOOLS,
                tool_choice="auto",
            )

            choice = response.choices[0]
            message = choice.message

            result = {
                "content": message.content or "",
                "tool_calls": [],
            }

            if message.tool_calls:
                for tc in message.tool_calls:
                    result["tool_calls"].append({
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments),
                    })

            return result

        except Exception as e:
            logger.exception(f"Error calling OpenRouter with model {self.model}")
            return {"content": f"Error: {str(e)}", "tool_calls": []}

    def _call_ai_with_tools_streaming(self, messages: List[Dict]) -> Generator[Dict[str, Any], None, None]:
        """Call OpenRouter with tool definitions (streaming).

        Yields:
        - {"type": "token", "content": str} for content tokens
        - {"type": "tool_call_detected"} when first tool call is detected (stop streaming tokens)
        - {"type": "result", "content": str, "tool_calls": list} at the end
        """
        try:
            if not self.openrouter_client:
                yield {"type": "result", "content": "OpenRouter API not configured.", "tool_calls": []}
                return

            logger.info(f"Streaming from OpenRouter with model: {self.model}")

            stream = self.openrouter_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=DISCUSSION_TOOLS,
                tool_choice="auto",
                stream=True,
            )

            content_chunks = []
            tool_calls_data = {}  # {index: {"id": ..., "name": ..., "arguments": ...}}
            tool_call_signaled = False

            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                # Handle content tokens
                if delta.content:
                    content_chunks.append(delta.content)
                    # Only yield tokens if we haven't detected a tool call yet
                    if not tool_call_signaled:
                        yield {"type": "token", "content": delta.content}

                # Handle tool calls (accumulated across chunks)
                if delta.tool_calls:
                    # Signal tool call detection ONCE so caller knows to stop streaming
                    if not tool_call_signaled:
                        tool_call_signaled = True
                        yield {"type": "tool_call_detected"}

                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}

                        if tc_chunk.id:
                            tool_calls_data[idx]["id"] = tc_chunk.id
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                tool_calls_data[idx]["name"] = tc_chunk.function.name
                            if tc_chunk.function.arguments:
                                tool_calls_data[idx]["arguments"] += tc_chunk.function.arguments

            # Parse accumulated tool calls
            tool_calls = []
            for idx in sorted(tool_calls_data.keys()):
                tc = tool_calls_data[idx]
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": args,
                })

            yield {
                "type": "result",
                "content": "".join(content_chunks),
                "tool_calls": tool_calls,
            }

        except Exception as e:
            logger.exception(f"Error in streaming OpenRouter call with model {self.model}")
            yield {"type": "result", "content": f"Error: {str(e)}", "tool_calls": []}

    def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Execute with tool calling and streaming.

        OVERRIDE: Only streams the FINAL response, not intermediate thinking.
        - Tokens are streamed immediately until a tool call is detected
        - When tool call is detected mid-stream, remaining content is hidden
        - Status messages are shown during tool execution
        - Final response (no tool calls) is fully streamed
        """
        max_iterations = 8
        iteration = 0
        all_tool_results = []
        final_content_chunks = []

        recent_results = ctx.get("recent_search_results", [])
        logger.info(f"[OpenRouter Streaming] Starting with model: {self.model}, recent_search_results: {len(recent_results)} papers")

        while iteration < max_iterations:
            iteration += 1
            print(f"\n[OpenRouter Streaming] Iteration {iteration}, messages count: {len(messages)}")

            response_content = ""
            tool_calls = []
            iteration_content = []
            has_tool_call = False

            for event in self._call_ai_with_tools_streaming(messages):
                if event["type"] == "token":
                    iteration_content.append(event["content"])
                    # Stream tokens to client UNLESS we already know this iteration has tool calls
                    if not has_tool_call:
                        yield {"type": "token", "content": event["content"]}
                elif event["type"] == "tool_call_detected":
                    # Tool call detected mid-stream - stop streaming, buffer the rest
                    has_tool_call = True
                    logger.info("[OpenRouter Streaming] Tool call detected, stopping token stream")
                elif event["type"] == "result":
                    response_content = event["content"]
                    tool_calls = event.get("tool_calls", [])

            print(f"[OpenRouter Streaming] Got {len(tool_calls)} tool calls: {[tc.get('name') for tc in tool_calls]}")
            print(f"[OpenRouter Streaming] Content preview: {response_content[:100] if response_content else 'empty'}...")

            if not tool_calls:
                # No tool calls - this was the final response, already streamed
                logger.info("[OpenRouter Streaming] Final response - tokens already streamed")
                final_content_chunks.extend(iteration_content)
                break

            # Tool calls present - send status messages
            for tc in tool_calls:
                tool_name = tc.get("name", "")
                status_message = self._get_tool_status_message(tool_name)
                yield {"type": "status", "tool": tool_name, "message": status_message}

            # Execute tool calls
            tool_results = self._execute_tool_calls(tool_calls, ctx)
            all_tool_results.extend(tool_results)

            # Add assistant message with tool calls to conversation
            formatted_tool_calls = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    }
                }
                for tc in tool_calls
            ]

            messages.append({
                "role": "assistant",
                "content": response_content or "",
                "tool_calls": formatted_tool_calls,
            })

            # Add tool results to conversation
            for tool_call, result in zip(tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, default=str),
                })

        # Build final result
        final_message = "".join(final_content_chunks)
        print(f"\n[OpenRouter DEBUG] Complete. Tools called: {[t['name'] for t in all_tool_results]}")
        print(f"[OpenRouter DEBUG] Tool results: {all_tool_results[:2]}...")  # First 2 for brevity

        # AUTO-FIX: Detect if model output LaTeX but didn't call create_paper tool
        # Some models (e.g., DeepSeek) output LaTeX directly instead of calling tools
        create_paper_called = any(t.get("name") == "create_paper" for t in all_tool_results)
        if not create_paper_called and self._contains_latex_paper(final_message):
            logger.info("[OpenRouter] Detected LaTeX paper content without create_paper call - auto-invoking tool")
            auto_result = self._auto_create_paper_from_content(ctx, final_message)
            if auto_result and auto_result.get("status") == "success":
                all_tool_results.append({"name": "create_paper", **auto_result})
                # Update message to show paper was created
                paper_title = auto_result.get("action", {}).get("payload", {}).get("title", "paper")
                final_message = f"Created a new paper in your project:\n\n**{paper_title}**\n\nYou can find it in the Papers section."
                yield {"type": "status", "tool": "create_paper", "message": "Creating paper"}

        actions = self._extract_actions(final_message, all_tool_results)
        print(f"[OpenRouter DEBUG] Extracted actions: {actions}")

        # Update AI memory after successful response
        contradiction_warning = None
        try:
            contradiction_warning = self.update_memory_after_exchange(
                ctx["channel"],
                ctx["user_message"],
                final_message,
                ctx.get("conversation_history", []),
            )
            if contradiction_warning:
                logger.info(f"Contradiction detected: {contradiction_warning}")
        except Exception as mem_err:
            logger.error(f"Failed to update AI memory: {mem_err}")

        yield {
            "type": "result",
            "data": {
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": [t["name"] for t in all_tool_results] if all_tool_results else [],
                "conversation_state": {},
                "memory_warning": contradiction_warning,
            }
        }

    def _contains_latex_paper(self, content: str) -> bool:
        """Check if content contains LaTeX paper indicators."""
        import re
        if not content:
            return False
        # Look for LaTeX document patterns
        latex_indicators = [
            r'\\documentclass',
            r'\\begin\{document\}',
            r'\\title\{',
            r'\\section\{',
            r'\\subsection\{',
            r'\\usepackage',
        ]
        # Need at least 2 indicators to be confident it's a paper
        matches = sum(1 for pattern in latex_indicators if re.search(pattern, content))
        return matches >= 2

    def _auto_create_paper_from_content(self, ctx: Dict[str, Any], content: str) -> Optional[Dict]:
        """Extract LaTeX content and auto-create paper when model didn't call tool."""
        import re

        try:
            # Extract title from \title{...} if present
            title_match = re.search(r'\\title\{([^}]+)\}', content)
            title = title_match.group(1) if title_match else "Untitled Paper"
            # Clean up title (remove LaTeX commands)
            title = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', title)
            title = re.sub(r'\\\\', ' ', title).strip()

            # Extract abstract if present
            abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', content, re.DOTALL)
            abstract = abstract_match.group(1).strip() if abstract_match else None

            # Extract the LaTeX content (could be in code block or raw)
            # Try to find content in code block first
            code_block_match = re.search(r'```(?:latex|tex)?\s*(.*?)```', content, re.DOTALL)
            if code_block_match:
                latex_content = code_block_match.group(1).strip()
            else:
                # Use the raw content but try to extract from \documentclass to \end{document}
                doc_match = re.search(r'(\\documentclass.*?\\end\{document\})', content, re.DOTALL)
                if doc_match:
                    latex_content = doc_match.group(1)
                else:
                    # Just use the content as-is
                    latex_content = content

            logger.info(f"[OpenRouter] Auto-creating paper: {title}")
            result = self._tool_create_paper(ctx, title=title, content=latex_content, abstract=abstract)
            return result

        except Exception as e:
            logger.error(f"[OpenRouter] Failed to auto-create paper: {e}")
            return None


def get_available_models() -> List[Dict[str, str]]:
    """Return list of available models for the frontend."""
    return [
        {"id": model_id, **info}
        for model_id, info in OPENROUTER_MODELS.items()
    ]
