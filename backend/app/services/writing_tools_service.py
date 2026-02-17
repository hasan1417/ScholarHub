import logging
import time
from typing import List, Dict, Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class WritingToolsMixin:

    def generate_text(self, text: str, instruction: str, context: Optional[str] = None, max_length: int = 500) -> Dict[str, Any]:
        try:
            start_time = time.time()
            writing_model = self.writing_model
            logger.info(f"Generating text with instruction: {instruction} using model {writing_model}")

            if not self.openai_client:
                raise ValueError("OpenAI client is not configured - cannot generate text")

            clean_instruction = (instruction or "").strip()
            has_text = bool(text and str(text).strip())
            prompt_parts = []

            if has_text:
                if clean_instruction.lower() == "expand":
                    prompt_parts.append("Expand the following text, making it more detailed and comprehensive while maintaining the same tone and style. Add relevant examples, explanations, and context.")
                elif clean_instruction.lower() == "rephrase":
                    prompt_parts.append("Rephrase the following text while keeping the same meaning and academic tone.")
                elif clean_instruction.lower() == "complete":
                    prompt_parts.append("Complete the following text, continuing the thought naturally and maintaining the same style and tone.")
                elif clean_instruction.lower() == "summarize":
                    prompt_parts.append("Summarize the following text concisely, capturing the key points and main ideas.")
                else:
                    prompt_parts.append(f"{clean_instruction} the following text.")
                prompt_parts.append(text or "")
            else:
                prompt_parts.append(f"{clean_instruction or 'Generate new content'} even if no input text is provided.")

            if context:
                prompt_parts.append(f"Use this context when helpful:\n{context}")

            prompt_parts.append(f"Return concise, publication-ready prose. Keep the response within roughly {max_length} words.")
            prompt_parts.append("If LaTeX markup is present or implied, keep it intact and avoid adding documentclass/preamble unless explicitly asked. Do not wrap the answer in Markdown fences.")

            prompt = "\n\n".join(part for part in prompt_parts if part)

            response = self.create_response(
                messages=[
                    {"role": "system", "content": "You are an expert academic writing assistant. Respond in plain text without Markdown fences. Preserve any LaTeX already present and, when the task implies LaTeX, produce LaTeX-ready output using standard commands (e.g., \\section, \\begin{itemize}) without adding a preamble."},
                    {"role": "user", "content": prompt}
                ],
                model=writing_model,
                max_output_tokens=min(max_length * 2, 2000),
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
            raise

    def check_grammar_and_style(self, text: str, check_grammar: bool = True, check_style: bool = True, check_clarity: bool = True) -> Dict[str, Any]:
        try:
            start_time = time.time()
            writing_model = self.writing_model
            logger.info(f"Performing grammar and style check using model {writing_model}")

            if not self.openai_client:
                raise ValueError("OpenAI client is not configured - cannot check grammar")

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

            result = self._parse_grammar_response(response_text, text)
            result['processing_time'] = processing_time

            logger.info(f"Grammar check completed in {processing_time:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Error in grammar check: {str(e)}")
            raise

    def enhance_with_research_context(self, text: str, paper_ids: List[str], query_type: str, user_id: str) -> Dict[str, Any]:
        try:
            start_time = time.time()
            writing_model = self.writing_model
            logger.info(f"Enhancing text with research context: {query_type} using model {writing_model}")

            if not self.openai_client:
                raise ValueError("OpenAI client is not configured - cannot enhance text")

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
                'relevant_sources': [],
                'processing_time': processing_time
            }

        except Exception as e:
            logger.error(f"Error in research context enhancement: {str(e)}")
            raise

    def stream_generate_text(self, text: str, instruction: str, context: Optional[str] = None, max_length: int = 500):
        if not self.openai_client:
            raise ValueError("OpenAI client is not configured - cannot generate text")

        clean_instruction = (instruction or "").strip()
        has_text = bool(text and str(text).strip())
        prompt_parts = []

        if has_text:
            if clean_instruction.lower() == "expand":
                prompt_parts.append("Expand the following text, making it more detailed and comprehensive while maintaining the same tone and style. Add relevant examples, explanations, and context.")
            elif clean_instruction.lower() == "rephrase":
                prompt_parts.append("Rephrase the following text while keeping the same meaning and academic tone.")
            elif clean_instruction.lower() == "complete":
                prompt_parts.append("Complete the following text, continuing the thought naturally and maintaining the same style and tone.")
            elif clean_instruction.lower() == "summarize":
                prompt_parts.append("Summarize the following text concisely, capturing the key points and main ideas.")
            else:
                prompt_parts.append(f"{clean_instruction} the following text.")
            prompt_parts.append(text or "")
        else:
            prompt_parts.append(f"{clean_instruction or 'Generate new content'} even if no input text is provided.")

        if context:
            prompt_parts.append(f"Use this context when helpful:\n{context}")

        prompt_parts.append(f"Return concise, publication-ready prose. Keep the response within roughly {max_length} words.")
        prompt_parts.append("If LaTeX markup is present or implied, keep it intact and avoid adding documentclass/preamble unless explicitly asked. Do not wrap the answer in Markdown fences.")

        prompt = "\n\n".join(part for part in prompt_parts if part)

        try:
            messages = [
                {"role": "system", "content": "You are an expert academic writing assistant. Respond in plain text (no Markdown fences). Preserve any LaTeX already present and, when the task implies LaTeX, produce LaTeX-ready output using standard commands without adding a preamble."},
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

    def _parse_grammar_response(self, response_text: str, original_text: str) -> Dict[str, Any]:
        try:
            corrected_text = original_text
            suggestions = []
            score = 85.0

            lines = response_text.split('\n')
            for line in lines:
                if line.startswith('CORRECTED_TEXT:'):
                    corrected_text = line.replace('CORRECTED_TEXT:', '').strip()
                elif line.startswith('SUGGESTIONS:'):
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
            return {
                'corrected_text': original_text,
                'original_text': original_text,
                'suggestions': ["Error parsing AI response. Please try again."],
                'overall_score': 85.0
            }
