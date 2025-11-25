"""
Literature Review Service - AI-powered automated literature review generation
"""

import logging
import time
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from openai import OpenAI
from sqlalchemy.orm import Session

from app.models.research_paper import ResearchPaper
from app.models.document import Document
from app.models.document_chunk import DocumentChunk

logger = logging.getLogger(__name__)


@dataclass
class PaperSummary:
    """Summary of a research paper for literature review"""
    paper_id: str
    title: str
    authors: List[str]
    year: Optional[int]
    key_findings: List[str]
    methodology: str
    limitations: List[str]
    themes: List[str]
    citation_text: str


@dataclass
class ReviewSection:
    """A section of the literature review"""
    title: str
    content: str
    papers_cited: List[str]
    themes: List[str]


@dataclass
class LiteratureReview:
    """Complete literature review structure"""
    title: str
    abstract: str
    introduction: str
    methodology: str
    sections: List[ReviewSection]
    synthesis: str
    research_gaps: List[str]
    future_directions: List[str]
    conclusion: str
    references: List[str]
    total_papers: int
    generation_time: float


class LiteratureReviewService:
    """
    Service for generating automated literature reviews from research papers
    """
    
    def __init__(self):
        self.openai_client = None
        
        # Initialize OpenAI client
        try:
            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                self.openai_client = OpenAI(api_key=api_key)
                logger.info("OpenAI client initialized for literature review service")
            else:
                logger.warning("No OpenAI API key found - literature review generation will be limited")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}")

    def _create_response(
        self,
        messages: List[Dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
    ):
        if not self.openai_client:
            raise ValueError("OpenAI client not initialized")

        payload: Dict[str, Any] = {
            "model": model,
            "input": messages,
            "temperature": temperature,
        }
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens

        return self.openai_client.responses.create(**payload)

    @staticmethod
    def _extract_text(response: Any) -> str:
        return (getattr(response, "output_text", "") or "").strip()
    
    async def generate_literature_review(
        self,
        db: Session,
        paper_ids: List[str],
        review_topic: str,
        user_id: str,
        review_type: str = "systematic",  # 'systematic', 'narrative', 'scoping'
        max_sections: int = 6
    ) -> LiteratureReview:
        """
        Generate a comprehensive literature review from selected papers
        
        Args:
            db: Database session
            paper_ids: List of paper IDs to include in review
            review_topic: Main topic/research question for the review
            user_id: User requesting the review
            review_type: Type of review to generate
            max_sections: Maximum number of main sections
        
        Returns:
            Generated literature review
        """
        logger.info(f"Generating {review_type} literature review for {len(paper_ids)} papers")
        start_time = time.time()
        
        if not self.openai_client:
            logger.error("Cannot generate literature review without OpenAI client")
            raise ValueError("AI service not available for literature review generation")
        
        # Load and analyze papers
        paper_summaries = await self._analyze_papers(db, paper_ids, user_id)
        
        if not paper_summaries:
            raise ValueError("No valid papers found for literature review generation")
        
        # Identify themes and structure
        themes = await self._identify_themes(paper_summaries, review_topic)
        
        # Generate review sections
        sections = await self._generate_review_sections(paper_summaries, themes, review_topic, max_sections)
        
        # Generate introduction and conclusion
        introduction = await self._generate_introduction(paper_summaries, review_topic, review_type)
        abstract = await self._generate_abstract(paper_summaries, sections, review_topic)
        methodology = await self._generate_methodology_section(review_type, len(paper_summaries))
        synthesis = await self._generate_synthesis(sections, paper_summaries, review_topic)
        research_gaps = await self._identify_research_gaps(paper_summaries, review_topic)
        future_directions = await self._generate_future_directions(research_gaps, review_topic)
        conclusion = await self._generate_conclusion(synthesis, research_gaps, review_topic)
        
        # Generate references
        references = [summary.citation_text for summary in paper_summaries if summary.citation_text]
        
        # Create review title
        title = await self._generate_review_title(review_topic, review_type)
        
        generation_time = time.time() - start_time
        
        review = LiteratureReview(
            title=title,
            abstract=abstract,
            introduction=introduction,
            methodology=methodology,
            sections=sections,
            synthesis=synthesis,
            research_gaps=research_gaps,
            future_directions=future_directions,
            conclusion=conclusion,
            references=references,
            total_papers=len(paper_summaries),
            generation_time=generation_time
        )
        
        logger.info(f"Literature review generated in {generation_time:.2f}s")
        return review
    
    async def _analyze_papers(self, db: Session, paper_ids: List[str], user_id: str) -> List[PaperSummary]:
        """Analyze papers and extract key information"""
        summaries = []
        
        for paper_id in paper_ids:
            try:
                # Get paper from database
                paper = db.query(ResearchPaper).filter(
                    ResearchPaper.id == paper_id,
                    ResearchPaper.owner_id == user_id  # Security check
                ).first()
                
                if not paper:
                    logger.warning(f"Paper {paper_id} not found or not accessible")
                    continue
                
                # Get document content if available
                content = ""
                if paper.content:
                    content = paper.content
                elif paper.content_json:
                    # Extract text from TipTap JSON if needed
                    content = self._extract_text_from_tiptap_json(paper.content_json)
                
                # Get chunks if available for more detailed analysis
                chunks = []
                if content:
                    document = db.query(Document).filter(Document.id == paper.id).first()
                    if document:
                        chunks = db.query(DocumentChunk).filter(
                            DocumentChunk.document_id == document.id
                        ).all()
                
                # Analyze paper content
                summary = await self._analyze_single_paper(paper, content, chunks)
                if summary:
                    summaries.append(summary)
                    
            except Exception as e:
                logger.error(f"Error analyzing paper {paper_id}: {e}")
                continue
        
        logger.info(f"Analyzed {len(summaries)} papers successfully")
        return summaries
    
    async def _analyze_single_paper(
        self, 
        paper: ResearchPaper, 
        content: str, 
        chunks: List[DocumentChunk] = None
    ) -> Optional[PaperSummary]:
        """Analyze a single paper and extract key information"""
        try:
            # Combine available text
            text_to_analyze = f"Title: {paper.title}\n"
            if paper.description:
                text_to_analyze += f"Description: {paper.description}\n"
            if content:
                text_to_analyze += f"Content: {content[:5000]}...\n"  # Limit content length
            
            # Create analysis prompt
            prompt = f"""Analyze this research paper and extract key information:

{text_to_analyze}

Please provide:
1. Key findings (3-5 bullet points)
2. Methodology used (brief description)
3. Main limitations (2-3 points)
4. Key themes/topics (3-5 themes)

Format your response as:
KEY FINDINGS:
- [finding 1]
- [finding 2]
- [finding 3]

METHODOLOGY:
[methodology description]

LIMITATIONS:
- [limitation 1]
- [limitation 2]

THEMES:
- [theme 1]
- [theme 2]
- [theme 3]"""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert academic researcher who analyzes research papers and extracts key information for literature reviews."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=800,
                temperature=0.3
            )
            
            analysis = self._extract_text(response)
            
            # Parse the response
            parsed = self._parse_paper_analysis(analysis)
            
            # Create citation text
            authors_str = ", ".join(paper.authors[:3]) if hasattr(paper, 'authors') and paper.authors else "Unknown Authors"
            if len(paper.authors) > 3:
                authors_str += " et al."
            
            citation_text = f"{authors_str}. ({paper.year or 'n.d.'}). {paper.title}."
            
            return PaperSummary(
                paper_id=paper.id,
                title=paper.title,
                authors=paper.authors if hasattr(paper, 'authors') and paper.authors else [],
                year=paper.year,
                key_findings=parsed.get('key_findings', []),
                methodology=parsed.get('methodology', ''),
                limitations=parsed.get('limitations', []),
                themes=parsed.get('themes', []),
                citation_text=citation_text
            )
            
        except Exception as e:
            logger.error(f"Error analyzing paper {paper.id}: {e}")
            return None
    
    def _parse_paper_analysis(self, analysis: str) -> Dict[str, Any]:
        """Parse the AI analysis response"""
        result = {
            'key_findings': [],
            'methodology': '',
            'limitations': [],
            'themes': []
        }
        
        try:
            sections = analysis.split('\n\n')
            current_section = None
            
            for line in analysis.split('\n'):
                line = line.strip()
                
                if line.startswith('KEY FINDINGS:'):
                    current_section = 'key_findings'
                elif line.startswith('METHODOLOGY:'):
                    current_section = 'methodology'
                elif line.startswith('LIMITATIONS:'):
                    current_section = 'limitations'
                elif line.startswith('THEMES:'):
                    current_section = 'themes'
                elif line.startswith('- ') and current_section in ['key_findings', 'limitations', 'themes']:
                    result[current_section].append(line[2:])
                elif current_section == 'methodology' and line and not line.startswith('-'):
                    if result['methodology']:
                        result['methodology'] += ' '
                    result['methodology'] += line
            
        except Exception as e:
            logger.error(f"Error parsing analysis: {e}")
        
        return result
    
    async def _identify_themes(self, summaries: List[PaperSummary], topic: str) -> List[str]:
        """Identify major themes across papers"""
        try:
            all_themes = []
            for summary in summaries:
                all_themes.extend(summary.themes)
            
            themes_text = ", ".join(all_themes)
            
            prompt = f"""Given these themes from multiple research papers about "{topic}":
{themes_text}

Identify 4-6 major themes that could organize a literature review. Group similar themes together and provide clear, descriptive theme titles.

Provide themes as a simple list, one per line:"""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert at organizing research themes for literature reviews."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=300,
                temperature=0.3
            )
            
            themes = []
            for line in self._extract_text(response).split('\n'):
                theme = line.strip().lstrip('1234567890.- ')
                if theme and len(theme) > 3:
                    themes.append(theme)
            
            return themes[:6]  # Limit to 6 themes
            
        except Exception as e:
            logger.error(f"Error identifying themes: {e}")
            return ["Methodological Approaches", "Key Findings", "Limitations and Challenges", "Future Directions"]
    
    async def _generate_review_sections(
        self, 
        summaries: List[PaperSummary], 
        themes: List[str], 
        topic: str, 
        max_sections: int
    ) -> List[ReviewSection]:
        """Generate main sections of the literature review"""
        sections = []
        
        for i, theme in enumerate(themes[:max_sections]):
            try:
                # Find papers relevant to this theme
                relevant_papers = []
                for summary in summaries:
                    # Simple theme matching - could be improved with semantic similarity
                    theme_lower = theme.lower()
                    summary_themes_lower = [t.lower() for t in summary.themes]
                    
                    if any(theme_word in ' '.join(summary_themes_lower) for theme_word in theme_lower.split()):
                        relevant_papers.append(summary)
                
                if not relevant_papers:
                    # Include all papers if no specific matches
                    relevant_papers = summaries[:3]  # Limit to first 3
                
                # Generate section content
                content = await self._generate_section_content(theme, relevant_papers, topic)
                
                section = ReviewSection(
                    title=theme,
                    content=content,
                    papers_cited=[p.paper_id for p in relevant_papers],
                    themes=[theme]
                )
                sections.append(section)
                
            except Exception as e:
                logger.error(f"Error generating section for theme '{theme}': {e}")
                continue
        
        return sections
    
    async def _generate_section_content(
        self, 
        theme: str, 
        papers: List[PaperSummary], 
        topic: str
    ) -> str:
        """Generate content for a specific section"""
        try:
            papers_info = ""
            for paper in papers[:5]:  # Limit to 5 papers per section
                papers_info += f"""
Paper: {paper.title}
Authors: {', '.join(paper.authors[:3])}
Key Findings: {'; '.join(paper.key_findings[:3])}
Methodology: {paper.methodology[:200]}...
"""
            
            prompt = f"""Write a comprehensive literature review section about "{theme}" in the context of "{topic}".

Use the following research papers as sources:
{papers_info}

Write a well-structured section (400-600 words) that:
1. Introduces the theme and its importance
2. Synthesizes findings from the papers
3. Compares and contrasts different approaches
4. Identifies patterns and trends
5. Notes any contradictions or debates

Use academic writing style with proper citations (Author, Year format)."""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert academic writer specializing in literature reviews. Write comprehensive, well-cited sections."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-4",
                max_output_tokens=800,
                temperature=0.4
            )
            
            return self._extract_text(response)
            
        except Exception as e:
            logger.error(f"Error generating section content: {e}")
            return f"## {theme}\n\nThis section examines {theme.lower()} in the context of {topic}. [Content generation error - please review manually]"
    
    async def _generate_introduction(self, summaries: List[PaperSummary], topic: str, review_type: str) -> str:
        """Generate introduction section"""
        try:
            prompt = f"""Write an introduction for a {review_type} literature review on "{topic}".

This review covers {len(summaries)} research papers.

The introduction should (300-400 words):
1. Define the research area and its importance
2. Explain the purpose and scope of this review
3. Outline the review methodology
4. Preview the main sections and structure

Use academic writing style."""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert academic writer specializing in literature review introductions."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=500,
                temperature=0.4
            )
            
            return self._extract_text(response)
            
        except Exception as e:
            logger.error(f"Error generating introduction: {e}")
            return f"# Introduction\n\nThis {review_type} literature review examines {topic} through an analysis of {len(summaries)} research papers."
    
    async def _generate_abstract(self, summaries: List[PaperSummary], sections: List[ReviewSection], topic: str) -> str:
        """Generate abstract for the literature review"""
        try:
            section_titles = [s.title for s in sections]
            
            prompt = f"""Write an abstract for a literature review on "{topic}".

The review covers {len(summaries)} papers and includes sections on: {', '.join(section_titles)}.

The abstract should (150-200 words):
1. State the purpose of the review
2. Describe the methodology
3. Summarize key findings
4. Note implications and conclusions

Use academic style."""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert at writing concise, informative abstracts for academic literature reviews."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=300,
                temperature=0.3
            )
            
            return self._extract_text(response)
            
        except Exception as e:
            logger.error(f"Error generating abstract: {e}")
            return f"This literature review examines {topic} through systematic analysis of {len(summaries)} research papers."
    
    async def _generate_methodology_section(self, review_type: str, paper_count: int) -> str:
        """Generate methodology section"""
        method_descriptions = {
            'systematic': 'A systematic approach was used to identify, select, and analyze relevant literature.',
            'narrative': 'A narrative review approach was employed to synthesize existing knowledge.',
            'scoping': 'A scoping review methodology was used to map key concepts and evidence.'
        }
        
        description = method_descriptions.get(review_type, 'A comprehensive review approach was used.')
        
        return f"""## Methodology

{description} The review included {paper_count} research papers selected based on their relevance to the research topic. Papers were analyzed for key findings, methodological approaches, and theoretical contributions.

The analysis involved extracting key information from each paper, identifying common themes, and synthesizing findings to provide a comprehensive overview of the current state of knowledge in this field."""
    
    async def _generate_synthesis(self, sections: List[ReviewSection], summaries: List[PaperSummary], topic: str) -> str:
        """Generate synthesis section"""
        try:
            section_summaries = ""
            for section in sections:
                section_summaries += f"- {section.title}: {section.content[:200]}...\n"
            
            prompt = f"""Write a synthesis section for a literature review on "{topic}".

Based on these main sections:
{section_summaries}

The synthesis should (300-400 words):
1. Integrate findings across all sections
2. Identify overarching patterns and trends
3. Discuss theoretical contributions
4. Note methodological insights
5. Highlight key agreements and disagreements

Use academic writing style."""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert at synthesizing research findings across multiple studies and themes."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=500,
                temperature=0.4
            )
            
            return self._extract_text(response)
            
        except Exception as e:
            logger.error(f"Error generating synthesis: {e}")
            return "## Synthesis\n\nThe reviewed literature provides important insights into multiple aspects of the research topic."
    
    async def _identify_research_gaps(self, summaries: List[PaperSummary], topic: str) -> List[str]:
        """Identify research gaps from the literature"""
        try:
            limitations_text = ""
            for summary in summaries:
                limitations_text += f"- {'; '.join(summary.limitations)}\n"
            
            prompt = f"""Based on these limitations from research papers about "{topic}":

{limitations_text}

Identify 4-6 key research gaps that represent opportunities for future research. Focus on:
1. Methodological gaps
2. Theoretical gaps  
3. Empirical gaps
4. Practical applications

Provide as a simple list, one gap per line:"""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert at identifying research gaps and opportunities for future studies."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=300,
                temperature=0.3
            )
            
            gaps = []
            for line in self._extract_text(response).split('\n'):
                gap = line.strip().lstrip('1234567890.- ')
                if gap and len(gap) > 10:
                    gaps.append(gap)
            
            return gaps
            
        except Exception as e:
            logger.error(f"Error identifying research gaps: {e}")
            return ["Limited longitudinal studies", "Need for larger sample sizes", "Lack of cross-cultural validation"]
    
    async def _generate_future_directions(self, gaps: List[str], topic: str) -> List[str]:
        """Generate future research directions"""
        try:
            gaps_text = "\n".join([f"- {gap}" for gap in gaps])
            
            prompt = f"""Based on these research gaps in "{topic}":
{gaps_text}

Suggest 4-6 specific future research directions that would address these gaps. Make suggestions:
1. Specific and actionable
2. Methodologically sound
3. Theoretically grounded
4. Practically relevant

Provide as a simple list, one direction per line:"""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert researcher who provides specific, actionable suggestions for future research."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=300,
                temperature=0.4
            )
            
            directions = []
            for line in self._extract_text(response).split('\n'):
                direction = line.strip().lstrip('1234567890.- ')
                if direction and len(direction) > 10:
                    directions.append(direction)
            
            return directions
            
        except Exception as e:
            logger.error(f"Error generating future directions: {e}")
            return ["Conduct longitudinal studies", "Expand sample diversity", "Develop new methodological approaches"]
    
    async def _generate_conclusion(self, synthesis: str, gaps: List[str], topic: str) -> str:
        """Generate conclusion section"""
        try:
            prompt = f"""Write a conclusion for a literature review on "{topic}".

Based on the synthesis: {synthesis[:300]}...

And research gaps: {'; '.join(gaps)}

The conclusion should (200-300 words):
1. Summarize key contributions of the review
2. Restate main findings and implications
3. Acknowledge limitations of current research
4. Emphasize the importance of addressing research gaps
5. End with a forward-looking statement

Use academic writing style."""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert at writing compelling, comprehensive conclusions for academic literature reviews."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=400,
                temperature=0.4
            )
            
            return self._extract_text(response)
            
        except Exception as e:
            logger.error(f"Error generating conclusion: {e}")
            return f"## Conclusion\n\nThis literature review has examined current research on {topic} and identified several important findings and research directions."
    
    async def _generate_review_title(self, topic: str, review_type: str) -> str:
        """Generate an appropriate title for the literature review"""
        try:
            prompt = f"""Generate a compelling academic title for a {review_type} literature review about "{topic}".

The title should be:
1. Descriptive and specific
2. Academic in tone
3. 10-15 words long
4. Include the review type if appropriate

Provide just the title:"""

            response = self._create_response(
                messages=[
                    {"role": "system", "content": "You are an expert at creating compelling, descriptive academic titles."},
                    {"role": "user", "content": prompt}
                ],
                model="gpt-3.5-turbo",
                max_output_tokens=100,
                temperature=0.5
            )
            
            title = self._extract_text(response).strip('"')
            return title
            
        except Exception as e:
            logger.error(f"Error generating title: {e}")
            return f"A {review_type.title()} Literature Review of {topic}"
    
    def _extract_text_from_tiptap_json(self, json_content: Any) -> str:
        """Extract plain text from TipTap JSON content"""
        try:
            if isinstance(json_content, dict):
                text_parts = []
                
                def extract_text_recursive(node):
                    if isinstance(node, dict):
                        if node.get('text'):
                            text_parts.append(node['text'])
                        if node.get('content'):
                            for child in node['content']:
                                extract_text_recursive(child)
                    elif isinstance(node, list):
                        for item in node:
                            extract_text_recursive(item)
                
                extract_text_recursive(json_content)
                return ' '.join(text_parts)
                
        except Exception as e:
            logger.error(f"Error extracting text from TipTap JSON: {e}")
        
        return ""
