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
            latex_detected = False
            content_buffer = ""  # Buffer to detect LaTeX early

            for event in self._call_ai_with_tools_streaming(messages):
                if event["type"] == "token":
                    iteration_content.append(event["content"])
                    content_buffer += event["content"]

                    # Early LaTeX detection - check after accumulating some content
                    if not latex_detected and len(content_buffer) > 50:
                        if self._detect_paper_content(content_buffer):
                            latex_detected = True
                            logger.info("[OpenRouter Streaming] LaTeX/paper content detected early - stopping token stream")
                            # Send status message to show loading state
                            yield {"type": "status", "tool": "create_paper", "message": "Creating paper"}

                    # Stream tokens to client UNLESS tool call or LaTeX detected
                    if not has_tool_call and not latex_detected:
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
                # No tool calls - this was the final response
                logger.info("[OpenRouter Streaming] Final response - no more tool calls")
                # Use streamed tokens if available, otherwise fall back to response_content
                # (some models don't stream tokens, they return content only in the final result)
                if iteration_content:
                    final_content_chunks.extend(iteration_content)
                elif response_content:
                    final_content_chunks.append(response_content)
                    # Stream the content now since it wasn't streamed earlier
                    if not latex_detected:
                        yield {"type": "token", "content": response_content}
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

        # AUTO-FIX: Detect if model output paper content but didn't call create_paper tool
        # Some models (e.g., DeepSeek) output content directly instead of calling tools
        create_paper_called = any(t.get("name") == "create_paper" for t in all_tool_results)
        if not create_paper_called:
            paper_format = self._detect_paper_content(final_message)
            if paper_format:
                logger.info(f"[OpenRouter] Detected {paper_format} paper content without create_paper call - auto-invoking tool")
                auto_result = self._auto_create_paper_from_content(ctx, final_message, paper_format)
                if auto_result and auto_result.get("status") == "success":
                    # Use proper tool result structure for _extract_actions
                    all_tool_results.append({"name": "create_paper", "result": auto_result})
                    # Update message to match normal Discussion AI format
                    paper_title = auto_result.get("action", {}).get("payload", {}).get("title", "paper")
                    paper_id = auto_result.get("action", {}).get("payload", {}).get("paper_id", "")
                    refs_linked = auto_result.get("references_linked", 0)
                    ref_msg = f" Linked {refs_linked} references." if refs_linked > 0 else ""
                    final_message = f"Created a new literature review paper in your project:\n\n**{paper_title}**\n(paper id: {paper_id})\n\n{ref_msg}"

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

    def _detect_paper_content(self, content: str) -> Optional[str]:
        """Detect if content contains paper content (LaTeX or Markdown). Returns format or None."""
        import re
        if not content:
            return None

        # Check for LaTeX patterns
        latex_indicators = [
            r'\\documentclass',
            r'\\begin\{document\}',
            r'\\title\{',
            r'\\section\{',
            r'\\subsection\{',
            r'\\usepackage',
        ]
        latex_matches = sum(1 for pattern in latex_indicators if re.search(pattern, content))
        if latex_matches >= 2:
            return "latex"

        # Check for Markdown paper patterns (structured academic content)
        markdown_indicators = [
            r'^#\s+.+',  # H1 heading (title)
            r'^##\s+(?:Abstract|Introduction|Background|Methods|Results|Discussion|Conclusion|References)',  # Academic sections
            r'^###\s+',  # H3 subsections
            r'\*\*(?:Abstract|Keywords|Author).*?\*\*',  # Bold academic labels
        ]
        markdown_matches = sum(1 for pattern in markdown_indicators if re.search(pattern, content, re.MULTILINE | re.IGNORECASE))
        # Need title + at least one academic section
        has_title = bool(re.search(r'^#\s+.+', content, re.MULTILINE))
        if has_title and markdown_matches >= 2:
            return "markdown"

        return None

    def _auto_create_paper_from_content(self, ctx: Dict[str, Any], content: str, paper_format: str) -> Optional[Dict]:
        """Extract paper content and auto-create paper when model didn't call tool."""
        import re

        try:
            if paper_format == "latex":
                return self._extract_and_create_latex_paper(ctx, content)
            elif paper_format == "markdown":
                return self._extract_and_create_markdown_paper(ctx, content)
            return None
        except Exception as e:
            logger.error(f"[OpenRouter] Failed to auto-create paper: {e}")
            return None

    def _extract_and_create_latex_paper(self, ctx: Dict[str, Any], content: str) -> Optional[Dict]:
        """Extract LaTeX content and create paper."""
        import re

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
        code_block_match = re.search(r'```(?:latex|tex)?\s*(.*?)```', content, re.DOTALL)
        if code_block_match:
            latex_content = code_block_match.group(1).strip()
        else:
            doc_match = re.search(r'(\\documentclass.*?\\end\{document\})', content, re.DOTALL)
            if doc_match:
                latex_content = doc_match.group(1)
            else:
                latex_content = content

        logger.info(f"[OpenRouter] Auto-creating LaTeX paper: {title}")
        return self._tool_create_paper(ctx, title=title, content=latex_content, abstract=abstract)

    def _extract_and_create_markdown_paper(self, ctx: Dict[str, Any], content: str) -> Optional[Dict]:
        """Extract Markdown content and convert to LaTeX for paper creation."""
        import re

        # Extract title from first H1
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "Untitled Paper"

        # Extract abstract if present
        abstract_match = re.search(r'##\s*Abstract\s*\n+(.*?)(?=\n##|\Z)', content, re.DOTALL | re.IGNORECASE)
        abstract = abstract_match.group(1).strip() if abstract_match else None

        # Convert Markdown to LaTeX
        latex_content = self._markdown_to_latex(content, title)

        logger.info(f"[OpenRouter] Auto-creating paper from Markdown: {title}")
        return self._tool_create_paper(ctx, title=title, content=latex_content, abstract=abstract)

    def _markdown_to_latex(self, md_content: str, title: str) -> str:
        """Convert Markdown paper content to LaTeX."""
        import re

        # Remove the title (we'll use \title{} instead)
        content = re.sub(r'^#\s+.+\n*', '', md_content, count=1)

        # Convert ## headings to \section{}
        content = re.sub(r'^##\s+(.+)$', r'\\section{\1}', content, flags=re.MULTILINE)

        # Convert ### headings to \subsection{}
        content = re.sub(r'^###\s+(.+)$', r'\\subsection{\1}', content, flags=re.MULTILINE)

        # Convert #### headings to \subsubsection{}
        content = re.sub(r'^####\s+(.+)$', r'\\subsubsection{\1}', content, flags=re.MULTILINE)

        # Convert **bold** to \textbf{}
        content = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', content)

        # Convert *italic* to \textit{}
        content = re.sub(r'\*(.+?)\*', r'\\textit{\1}', content)

        # Convert bullet lists
        content = re.sub(r'^[-*]\s+(.+)$', r'\\item \1', content, flags=re.MULTILINE)

        # Wrap consecutive \item lines in itemize environment
        def wrap_itemize(match):
            items = match.group(0)
            return '\\begin{itemize}\n' + items + '\\end{itemize}'
        content = re.sub(r'((?:\\item .+\n?)+)', wrap_itemize, content)

        return content.strip()


def get_available_models() -> List[Dict[str, str]]:
    """Return list of available models for the frontend."""
    return [
        {"id": model_id, **info}
        for model_id, info in OPENROUTER_MODELS.items()
    ]
