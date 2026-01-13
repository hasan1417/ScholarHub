"""
Tool-Based Discussion AI Orchestrator

Uses OpenAI function calling to let the AI decide what context it needs.
Instead of hardcoding what data each skill uses, the AI calls tools on-demand.

KEY ARCHITECTURE: Code-enforced state machine controls what the LLM can do.
The LLM generates content within boundaries - it CANNOT override state rules.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

from app.services.discussion_ai.state_machine import (
    ConversationState,
    ConversationStateMachine,
    StateTransition,
)
from app.services.discussion_ai.intent_classifier import IntentClassifier

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Project, ProjectDiscussionChannel
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

# Tool definitions for OpenAI function calling
DISCUSSION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_search_results",
            "description": "Get papers from the most recent search. Use this FIRST when user says 'these papers', 'these references', 'the 5 papers', 'use them', or refers to papers that were just searched/found. This contains the papers from the last search action.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_references",
            "description": "Get papers/references from the user's project library (permanently saved papers). Use when user mentions 'my library', 'saved papers', 'my collection'. NOT for recently searched papers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic_filter": {
                        "type": "string",
                        "description": "Optional keyword to filter references by topic"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of references to return",
                        "default": 10
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "Search for papers online. For multiple topics, call this multiple times with count=1 each (results accumulate). Example: 5 topics → call 5 times, each with a specific topic query and count=1, to get 5 relevant papers total.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query. For recent papers, include year terms like '2023 2024' or 'recent'. For multiple topics, combine with OR."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of papers to find (use higher count for multiple topics)",
                        "default": 5
                    },
                    "min_year": {
                        "type": "integer",
                        "description": "Minimum publication year filter. Use for 'recent papers' requests (e.g., 2022 for last ~2 years)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_papers",
            "description": "Get the user's own draft papers/documents in this project. Use when user mentions 'my paper', 'my draft', 'the paper I'm writing'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_content": {
                        "type": "boolean",
                        "description": "Whether to include full paper content",
                        "default": False
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_info",
            "description": "Get information about the current research project (title, description, goals, keywords). Use when user asks about 'the project', 'project goals', or needs project context.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_channel_resources",
            "description": "Get papers/references specifically attached to this discussion channel. Use when user mentions 'channel papers' or papers in this specific discussion.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# Base system prompt - constraints are added dynamically by the state machine
BASE_SYSTEM_PROMPT = """You are an intelligent research assistant.

CRITICAL RULE - CONVERSATION CONTEXT OVER PROJECT CONTEXT:
- When user says "the above", "these topics", "related to this" → use the CONVERSATION history, NOT the project title
- The conversation history contains what the user ACTUALLY discussed
- The project title is just metadata - do NOT inject it into searches unless user explicitly asks about the project
- If conversation discussed "swarm intelligence", search for "swarm intelligence" NOT the project title

SEARCH STRATEGY:
- Match the user's requested count EXACTLY. If they ask for 5 references, return exactly 5.
- For N references across M topics: do M searches with count=1 each (one paper per topic)
- Results accumulate in the UI, so multiple searches are fine
- Do NOT do extra searches beyond what was requested
- Example: "5 topics and 5 references" → propose 5 topics, then 5 searches (count=1 each)
- IMPORTANT: When search_papers returns status="success", the search IS working. Papers will appear in the UI.
- NEVER apologize or say you "couldn't find papers" when searches are initiated - they WILL work.

TOOL USAGE:
- search_papers: For multiple topics, call multiple times with count=1 each. Results accumulate.
- get_recent_search_results: For "these papers", "use them"
- get_project_references: For "my library", "saved papers"
- get_project_info: ONLY when user explicitly asks about "the project", "project goals"

NEVER HALLUCINATE REFERENCES:
- Do NOT invent citations or paper titles from your training data
- ALWAYS use the search_papers tool to find real papers
- If user asks for references, call the tool FIRST before listing anything

Project (for reference only, do NOT inject into searches): {project_title}
Channel: {channel_name}
{context_summary}

{state_constraints}"""

# Constraint templates added by state machine
CONSTRAINT_CLARIFICATION = """
CURRENT MODE: CLARIFICATION
- Ask ONE short question with 2-3 options max
- Do NOT call any tools
- Keep the question simple and direct
- Example: "Do you want research papers or a list of subtopics?"
"""

CONSTRAINT_EXECUTE = """
CURRENT MODE: EXECUTE
- Proceed with the task immediately
- NO questions allowed - make reasonable choices if unsure
- Use tools as needed to complete the request
"""

CONSTRAINT_EXECUTE_WITH_CHOICE = """
CURRENT MODE: EXECUTE (User made a choice)
- User chose: {user_choice}
- Original request: {original_query}
- Proceed based on their choice - NO more questions
- Complete the task now
"""


class ToolOrchestrator:
    """
    AI orchestrator that uses tools to gather context dynamically.

    KEY ARCHITECTURE: Code-enforced state machine controls what the LLM can do.
    - IntentClassifier: Fast pattern matching to understand user intent
    - ConversationStateMachine: Deterministic rules (cannot be overridden by LLM)
    - Tool execution: Only when state machine allows it
    """

    def __init__(self, ai_service: "AIService", db: "Session"):
        self.ai_service = ai_service
        self.db = db
        self.model = "gpt-5.2"  # Use gpt-5.2 as requested
        self.intent_classifier = IntentClassifier()
        self.state_machine = ConversationStateMachine()

    def handle_message(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]] = None,
        previous_state_dict: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        Handle a user message using state-controlled tool-based AI.

        Flow:
        1. Load previous conversation state
        2. Classify user intent (fast pattern matching)
        3. Compute state transition (deterministic rules)
        4. Execute within boundaries set by state machine

        Args:
            conversation_history: Previous messages [{"role": "user"|"assistant", "content": "..."}]
                                  This provides context for references like "the above topics"

        Returns response dict AND new state to persist.
        """

        # 1. Load previous state
        previous_state = ConversationState.from_dict(previous_state_dict or {})
        print(f"\n[STATE] Input: phase={previous_state.phase.value}, clarification_asked={previous_state.clarification_asked}")

        # 1.5. SPECIAL CASE: User responding with a count after we asked
        import re
        if previous_state_dict and previous_state_dict.get("awaiting_count"):
            # Extract number from user's response
            count_match = re.search(r"(\d+)", message)
            if count_match:
                count = int(count_match.group(1))
                original_query = previous_state_dict.get("original_query", message)
                context_query = previous_state_dict.get("context_query")  # For context-based searches
                print(f"[COUNT_RESPONSE] User provided count: {count} for query: {original_query}")

                # If this was a context search, execute it directly
                if context_query:
                    print(f"[COUNT_RESPONSE] Context search with query: {context_query}")
                    self._max_search_calls = count
                    self._search_calls_made = 0
                    return self._execute_context_search(
                        project=project,
                        query=context_query,
                        count=count,
                    )

                # Now proceed with the original query + the specified count
                # Re-classify with the original query but inject the count
                from app.services.discussion_ai.state_machine import UserIntent, ClassifiedIntent

                # Create a classified intent with the count
                topic_match = re.search(r"(?:about|on|for|related\s+to)\s+(.+?)(?:\s*$|\s*\.|\s*\?)", original_query, re.IGNORECASE)
                topic = topic_match.group(1).strip() if topic_match else None

                classified_intent = ClassifiedIntent(
                    intent=UserIntent.SEARCH_PAPERS,
                    confidence=1.0,
                    needs_project_context=False,
                    needs_search_results=False,
                    needs_library=False,
                    extracted_topic=topic,
                    extracted_count=count,
                )

                # Reset state
                previous_state.clarification_asked = False
                previous_state.clarification_answered = True

                # Set the limit and proceed
                self._max_search_calls = count
                self._search_calls_made = 0
                print(f"[LIMIT] Count from user response: {count}")

                # Continue to execute with this classified intent
                from app.services.discussion_ai.state_machine import StateTransition, ConversationPhase
                transition = StateTransition(
                    action="execute",
                    new_state=ConversationState(
                        phase=ConversationPhase.EXECUTING,
                        clarification_asked=True,
                        clarification_answered=True,
                    ),
                    prompt_constraints={
                        "user_choice": str(count),
                        "original_query": original_query,
                    },
                )

                result = self._execute_with_constraints(
                    project=project,
                    channel=channel,
                    message=original_query,  # Use original query
                    recent_search_results=recent_search_results,
                    transition=transition,
                    classified_intent=classified_intent,
                    conversation_history=conversation_history,
                )
                result["conversation_state"] = transition.new_state.to_dict()
                return result

        # 2. Classify intent (fast, before main LLM)
        has_search_results = bool(recent_search_results)
        print(f"[CLASSIFY] Message: {message[:80]}")
        print(f"[CLASSIFY] Has search results: {has_search_results}")
        print(f"[CLASSIFY] Conversation history: {len(conversation_history) if conversation_history else 0} messages")

        classified_intent = self.intent_classifier.classify(
            message=message,
            previous_state=previous_state,
            has_search_results=has_search_results,
            conversation_history=conversation_history,  # For context-based search extraction
        )
        print(f"[INTENT] Result: intent={classified_intent.intent.value}, confidence={classified_intent.confidence:.2f}")
        print(f"[INTENT] needs_project={classified_intent.needs_project_context}")
        print(f"[INTENT] extracted_context_query={classified_intent.extracted_context_query}")

        # 2.5. SPECIAL HANDLING: Search from context (deterministic, bypass LLM)
        from app.services.discussion_ai.state_machine import UserIntent
        if classified_intent.intent == UserIntent.SEARCH_FROM_CONTEXT and classified_intent.extracted_context_query:
            # If no count specified, ask the user
            if classified_intent.extracted_count is None:
                print(f"[CONTEXT_SEARCH] No count specified - asking user")
                return {
                    "message": f"I found these topics from our conversation: **{classified_intent.extracted_context_query}**\n\nHow many papers would you like me to find for these topics?",
                    "actions": [],
                    "citations": [],
                    "model_used": "deterministic",
                    "reasoning_used": False,
                    "tools_called": [],
                    "conversation_state": {
                        "phase": "clarification_pending",
                        "clarification_asked": True,
                        "awaiting_count": True,
                        "original_query": message,
                        "context_query": classified_intent.extracted_context_query,
                    },
                }

            print(f"[CONTEXT_SEARCH] BYPASSING LLM - using extracted query: {classified_intent.extracted_context_query}")
            return self._execute_context_search(
                project=project,
                query=classified_intent.extracted_context_query,
                count=classified_intent.extracted_count,
            )

        # 3. Compute state transition (CODE ENFORCED - LLM cannot override)
        transition = self.state_machine.transition(
            current_state=previous_state,
            classified_intent=classified_intent,
            message=message,
        )
        logger.info(
            "State transition: action=%s, new_phase=%s",
            transition.action,
            transition.new_state.phase.value,
        )

        # 4. Execute within boundaries
        result = self._execute_with_constraints(
            project=project,
            channel=channel,
            message=message,
            recent_search_results=recent_search_results,
            transition=transition,
            classified_intent=classified_intent,
            conversation_history=conversation_history,
        )

        # Add new state to result for persistence
        result["conversation_state"] = transition.new_state.to_dict()

        return result

    def _execute_with_constraints(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]],
        transition: StateTransition,
        classified_intent: "ClassifiedIntent",
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Execute AI within the boundaries set by state machine."""

        # CODE-ENFORCED LIMIT: Extract user's requested count for search calls
        # This CANNOT be overridden by the LLM - it's enforced in _execute_tool_calls
        # If user didn't specify a count, we need to ask (no default)
        from app.services.discussion_ai.state_machine import UserIntent
        needs_search = classified_intent.intent in (
            UserIntent.SEARCH_PAPERS,
            UserIntent.SEARCH_FROM_CONTEXT,
            UserIntent.AMBIGUOUS_REQUEST,
        )

        if needs_search and classified_intent.extracted_count is None:
            # User wants to search but didn't specify how many - ask them
            print(f"[LIMIT] No count specified for search - asking user")
            return {
                "message": "How many papers/references would you like me to find?",
                "actions": [],
                "citations": [],
                "model_used": "deterministic",
                "reasoning_used": False,
                "tools_called": [],
                "conversation_state": {
                    "phase": "clarification_pending",
                    "clarification_asked": True,
                    "awaiting_count": True,
                    "original_query": message,
                },
            }

        self._max_search_calls = classified_intent.extracted_count or 999  # High default if somehow not set
        self._search_calls_made = 0
        print(f"[LIMIT] Max search calls allowed: {self._max_search_calls}")

        # Build context summary
        context_summary = self._build_context_summary(project, channel, recent_search_results)

        # Build state-specific constraints for prompt
        state_constraints = self._build_state_constraints(transition)

        # Build system prompt with constraints
        system_prompt = BASE_SYSTEM_PROMPT.format(
            project_title=project.title,
            channel_name=channel.name,
            context_summary=context_summary,
            state_constraints=state_constraints,
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Add conversation history if provided (for context like "the above topics")
        if conversation_history:
            # Limit to last 10 messages to avoid token explosion
            recent_history = conversation_history[-10:]

            # Build explicit summary of what was discussed (helps LLM understand context)
            assistant_content = [
                msg["content"] for msg in recent_history
                if msg["role"] == "assistant" and len(msg["content"]) > 50
            ]
            if assistant_content:
                # Add explicit context reminder
                last_assistant = assistant_content[-1][:1500]  # Last substantial AI response
                context_reminder = f"""
CONVERSATION CONTEXT (what was discussed above):
---
{last_assistant}
---
When user refers to "above topics", "these subjects", etc., use the topics from this context.
"""
                messages.append({"role": "system", "content": context_reminder})

            for msg in recent_history:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current user message
        messages.append({"role": "user", "content": message})

        # Store context for tool execution
        self._current_context = {
            "project": project,
            "channel": channel,
            "recent_search_results": recent_search_results,
        }

        # Determine if tools should be available based on action
        use_tools = transition.action in ("execute", "respond")

        if not use_tools:
            # Clarification mode - no tools, just ask the question
            return self._generate_clarification(messages, transition)

        # Execute mode - run AI with tools
        return self._execute_with_tools(messages, transition)

    def _build_state_constraints(self, transition: StateTransition) -> str:
        """Build constraint text based on state machine decision."""

        constraints = transition.prompt_constraints

        if transition.action == "ask_clarification":
            return CONSTRAINT_CLARIFICATION

        if transition.action == "execute":
            if constraints.get("user_choice"):
                return CONSTRAINT_EXECUTE_WITH_CHOICE.format(
                    user_choice=constraints.get("user_choice", ""),
                    original_query=constraints.get("original_query", ""),
                )
            return CONSTRAINT_EXECUTE

        # Default
        return CONSTRAINT_EXECUTE

    def _execute_context_search(
        self,
        project: "Project",
        query: str,
        count: int = 5,
    ) -> Dict[str, Any]:
        """
        Execute a search based on context extracted from conversation.

        This is DETERMINISTIC - bypasses LLM decision-making entirely.
        The query was extracted programmatically from conversation history.
        """
        logger.info(f"Context search: query='{query}', count={count}")

        # Build a simple response confirming the search
        message = f"Searching for {count} papers about: **{query}**\n\n(This query was extracted from our conversation about the topics discussed above.)"

        return {
            "message": message,
            "actions": [
                {
                    "type": "search_references",
                    "summary": f"Search for papers about: {query}",
                    "payload": {
                        "query": query,
                        "max_results": count,
                    }
                }
            ],
            "citations": [],
            "model_used": "deterministic",  # No LLM used
            "reasoning_used": False,
            "tools_called": ["context_extraction"],
            "conversation_state": {
                "phase": "executing",
                "clarification_asked": False,
                "original_intent": "search_from_context",
            },
        }

    def _generate_clarification(
        self,
        messages: List[Dict],
        transition: StateTransition,
    ) -> Dict[str, Any]:
        """Generate a clarification question (no tools)."""

        try:
            client = self.ai_service.openai_client
            if not client:
                return {
                    "message": "AI service not configured.",
                    "actions": [],
                    "citations": [],
                    "model_used": self.model,
                    "reasoning_used": False,
                    "tools_called": [],
                }

            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                # NO tools - just generate clarification question
            )

            return {
                "message": response.choices[0].message.content or "",
                "actions": [],
                "citations": [],
                "model_used": self.model,
                "reasoning_used": False,
                "tools_called": [],
            }

        except Exception as e:
            logger.exception("Error generating clarification")
            return {
                "message": f"Error: {str(e)}",
                "actions": [],
                "citations": [],
                "model_used": self.model,
                "reasoning_used": False,
                "tools_called": [],
            }

    def _execute_with_tools(
        self,
        messages: List[Dict],
        transition: StateTransition,
    ) -> Dict[str, Any]:
        """Execute with tool calling (state allows it)."""

        max_iterations = 5
        iteration = 0
        all_tool_results = []
        response = {"content": "", "tool_calls": []}

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Tool orchestrator iteration {iteration}")

            response = self._call_ai_with_tools(messages)
            tool_calls = response.get("tool_calls", [])

            if not tool_calls:
                break

            # Execute tool calls
            tool_results = self._execute_tool_calls(tool_calls)
            all_tool_results.extend(tool_results)

            # Add assistant message with tool calls
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
                "content": response.get("content") or "",
                "tool_calls": formatted_tool_calls,
            })

            # Add tool results
            for tool_call, result in zip(tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(result, default=str),
                })

        final_message = response.get("content", "")
        actions = self._extract_actions(final_message, all_tool_results)

        return {
            "message": final_message,
            "actions": actions,
            "citations": [],
            "model_used": self.model,
            "reasoning_used": True,
            "tools_called": [t["name"] for t in all_tool_results] if all_tool_results else [],
        }

    def _build_context_summary(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        recent_search_results: Optional[List[Dict]],
    ) -> str:
        """Build a lightweight summary of available context."""

        lines = []

        # Count project references
        from app.models import ProjectReference
        ref_count = self.db.query(ProjectReference).filter(
            ProjectReference.project_id == project.id
        ).count()
        if ref_count > 0:
            lines.append(f"- Project library: {ref_count} saved references")

        # Count project papers
        from app.models import ResearchPaper
        paper_count = self.db.query(ResearchPaper).filter(
            ResearchPaper.project_id == project.id
        ).count()
        if paper_count > 0:
            lines.append(f"- Project papers: {paper_count} drafts")

        # Recent search results - show what's available
        if recent_search_results:
            lines.append(f"- Recent search results: {len(recent_search_results)} papers available:")
            for i, p in enumerate(recent_search_results[:5], 1):
                title = p.get("title", "Untitled")[:60]
                year = p.get("year", "")
                lines.append(f"    {i}. {title}{'...' if len(p.get('title', '')) > 60 else ''} ({year})")

        # Channel resources
        from app.models import ProjectDiscussionChannelResource
        resource_count = self.db.query(ProjectDiscussionChannelResource).filter(
            ProjectDiscussionChannelResource.channel_id == channel.id
        ).count()
        if resource_count > 0:
            lines.append(f"- Channel resources: {resource_count} attached")

        if not lines:
            lines.append("- No papers or references loaded yet")

        return "\n".join(lines)

    def _call_ai_with_tools(self, messages: List[Dict]) -> Dict[str, Any]:
        """Call OpenAI with tool definitions."""

        try:
            # Use the AI service's OpenAI client for tool calling
            client = self.ai_service.openai_client

            if not client:
                return {"content": "AI service not configured. Please check your OpenAI API key.", "tool_calls": []}

            response = client.chat.completions.create(
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
            logger.exception("Error calling AI with tools")
            return {"content": f"Error: {str(e)}", "tool_calls": []}

    def _execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Execute the tool calls and return results.

        CODE-ENFORCED LIMIT: search_papers calls are limited to _max_search_calls.
        This ensures the LLM cannot do more searches than the user requested.
        """

        results = []

        for tc in tool_calls:
            name = tc["name"]
            args = tc["arguments"]

            logger.info(f"Executing tool: {name} with args: {args}")

            try:
                # CODE-ENFORCED LIMIT: Block excess search_papers calls
                if name == "search_papers":
                    max_allowed = getattr(self, '_max_search_calls', 5)
                    calls_made = getattr(self, '_search_calls_made', 0)

                    if calls_made >= max_allowed:
                        print(f"[LIMIT] BLOCKED search_papers call #{calls_made + 1} (max: {max_allowed})")
                        result = {
                            "status": "blocked",
                            "message": f"Search limit reached ({max_allowed} searches). No more searches will be executed.",
                            "reason": "code_enforced_limit"
                        }
                        results.append({"name": name, "result": result})
                        continue

                    # Increment counter BEFORE executing
                    self._search_calls_made = calls_made + 1
                    print(f"[LIMIT] Executing search_papers call #{self._search_calls_made} of {max_allowed}")

                if name == "get_recent_search_results":
                    result = self._tool_get_recent_search_results()
                elif name == "get_project_references":
                    result = self._tool_get_project_references(**args)
                elif name == "search_papers":
                    result = self._tool_search_papers(**args)
                elif name == "get_project_papers":
                    result = self._tool_get_project_papers(**args)
                elif name == "get_project_info":
                    result = self._tool_get_project_info()
                elif name == "get_channel_resources":
                    result = self._tool_get_channel_resources()
                else:
                    result = {"error": f"Unknown tool: {name}"}

                results.append({"name": name, "result": result})

            except Exception as e:
                logger.exception(f"Error executing tool {name}")
                results.append({"name": name, "error": str(e)})

        return results

    def _tool_get_recent_search_results(self) -> Dict:
        """Get papers from the most recent search (passed from frontend)."""

        recent = self._current_context.get("recent_search_results", [])

        if not recent:
            return {
                "count": 0,
                "papers": [],
                "message": "No recent search results available. The user may need to search for papers first, or the search results weren't passed to this conversation."
            }

        return {
            "count": len(recent),
            "papers": [
                {
                    "title": p.get("title", "Untitled"),
                    "authors": p.get("authors", "Unknown"),
                    "year": p.get("year"),
                    "source": p.get("source", ""),
                    "abstract": p.get("abstract", "")[:500] if p.get("abstract") else "",
                    "doi": p.get("doi"),
                    "url": p.get("url"),
                }
                for p in recent
            ],
            "message": f"Found {len(recent)} papers from the recent search."
        }

    def _tool_get_project_references(
        self,
        topic_filter: Optional[str] = None,
        limit: int = 10,
    ) -> Dict:
        """Get references from project library."""

        from app.models import ProjectReference, Reference

        project = self._current_context["project"]

        query = self.db.query(Reference).join(
            ProjectReference,
            ProjectReference.reference_id == Reference.id
        ).filter(
            ProjectReference.project_id == project.id
        )

        # Apply topic filter if provided
        if topic_filter:
            query = query.filter(
                Reference.title.ilike(f"%{topic_filter}%") |
                Reference.abstract.ilike(f"%{topic_filter}%")
            )

        references = query.limit(limit).all()

        return {
            "count": len(references),
            "references": [
                {
                    "id": str(ref.id),
                    "title": ref.title,
                    "authors": ref.authors if isinstance(ref.authors, str) else ", ".join(ref.authors or []),
                    "year": ref.year,
                    "abstract": (ref.abstract or "")[:300],
                    "source": ref.source,
                }
                for ref in references
            ]
        }

    def _tool_search_papers(self, query: str, count: int = 5, min_year: int = None) -> Dict:
        """Search for papers online - returns action for frontend to execute."""

        # If min_year specified, append year terms to query for better results
        search_query = query
        if min_year:
            search_query = f"{query} {min_year}-{2026}"  # Include year range in query

        # Check if we have recent search results that match
        recent = self._current_context.get("recent_search_results", [])

        if recent:
            # Check if recent results might be relevant
            query_lower = query.lower()
            relevant = [
                r for r in recent
                if query_lower in r.get("title", "").lower() or
                   query_lower in r.get("abstract", "").lower()
            ]

            if relevant:
                return {
                    "status": "found_in_recent",
                    "count": len(relevant),
                    "papers": relevant[:count],
                    "message": f"Found {len(relevant)} relevant papers from recent search"
                }

        # Return action to trigger search
        # IMPORTANT: The response must clearly tell the AI that the search WILL succeed
        # so it doesn't apologize or say it couldn't find papers
        year_note = f" (from {min_year} onwards)" if min_year else ""
        payload = {
            "query": search_query,  # Use modified query with year if specified
            "max_results": count,
        }
        if min_year:
            payload["min_year"] = min_year

        return {
            "status": "success",
            "query": search_query,
            "count": count,
            "message": f"Search initiated for '{query}'{year_note}. Papers will appear in the results panel.",
            "action": {
                "type": "search_references",
                "payload": payload,
            },
            "note": "SEARCH IS SUCCESSFUL. Papers are being retrieved. Do NOT say you couldn't find papers or apologize. The search works."
        }

    def _tool_get_project_papers(self, include_content: bool = False) -> Dict:
        """Get user's draft papers in the project."""

        from app.models import ResearchPaper

        project = self._current_context["project"]

        papers = self.db.query(ResearchPaper).filter(
            ResearchPaper.project_id == project.id
        ).all()

        result = {
            "count": len(papers),
            "papers": []
        }

        for paper in papers:
            paper_info = {
                "id": str(paper.id),
                "title": paper.title,
                "status": paper.status,
                "paper_type": paper.paper_type,
                "abstract": paper.abstract,
            }

            if include_content and paper.content:
                # Truncate content to avoid token explosion
                paper_info["content"] = paper.content[:2000] + "..." if len(paper.content) > 2000 else paper.content

            result["papers"].append(paper_info)

        return result

    def _tool_get_project_info(self) -> Dict:
        """Get project information."""

        project = self._current_context["project"]

        return {
            "id": str(project.id),
            "title": project.title,
            "idea": project.idea or "",  # Project idea/description
            "scope": project.scope or "",  # Project scope
            "keywords": project.keywords or [],
            "status": project.status or "active",
        }

    def _tool_get_channel_resources(self) -> Dict:
        """Get resources attached to the current channel."""

        from app.models import ProjectDiscussionChannelResource, Reference, ResearchPaper

        channel = self._current_context["channel"]

        resources = self.db.query(ProjectDiscussionChannelResource).filter(
            ProjectDiscussionChannelResource.channel_id == channel.id
        ).all()

        result = {
            "count": len(resources),
            "resources": []
        }

        for res in resources:
            resource_info = {
                "id": str(res.id),
                "type": res.resource_type.value if hasattr(res.resource_type, 'value') else str(res.resource_type),
                "details": res.details or {},
            }
            result["resources"].append(resource_info)

        return result

    def _extract_actions(
        self,
        message: str,
        tool_results: List[Dict],
    ) -> List[Dict]:
        """Extract any actions that should be sent to the frontend."""

        actions = []

        # Check if any tool returned a search action
        for tr in tool_results:
            result = tr.get("result", {})
            if isinstance(result, dict) and result.get("action"):
                actions.append(result["action"])

        return actions

