"""Claude API integration for concept extraction.

Extracts concepts and relationships from text chunks using Claude.
Implements structured output parsing with retry logic.
"""

import json
import os
import time
from typing import TypedDict

import anthropic
from anthropic import RateLimitError, APIError

from .logging_utils import structured_logger

# Model configuration
EXTRACTION_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024

# Initialize client lazily
_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    """Get or create Anthropic client."""
    global _client
    if _client is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# Concept extraction prompt
EXTRACTION_PROMPT = """You are extracting concepts from text about data management and leadership.

## CONCEPT CATEGORIES (only use these)
- methodology: frameworks, approaches (e.g., "data mesh", "agile", "scrum")
- principle: core beliefs, guiding rules (e.g., "domain ownership", "single responsibility")
- pattern: recurring solutions (e.g., "event sourcing", "CQRS", "data product")
- role: people, teams, responsibilities (e.g., "data product owner", "platform team")
- tool: technologies, products (e.g., "dbt", "Kafka", "Snowflake")
- metric: measurements, KPIs (e.g., "data quality score", "lead time")

## RELATIONSHIP TYPES (only use these)
- enables: A makes B possible (e.g., "domain ownership enables data product")
- requires: A depends on B (e.g., "data product requires clear ownership")
- part_of: A is a component of B (e.g., "schema is part_of data product")
- similar_to: A is conceptually like B (e.g., "data mesh similar_to microservices")
- contrasts: A is the opposite of B (e.g., "centralized contrasts federated")

## RULES
1. Only extract SPECIFIC concepts that are REUSABLE across documents
2. Do NOT extract generic terms: "data", "team", "process", "system", "organization"
3. Normalize names: lowercase, singular form (e.g., "data product" not "Data Products")
4. Only create relationships explicitly stated or strongly implied in the text
5. Include a brief description for each concept

## TEXT TO ANALYZE
\"\"\"
{text}
\"\"\"

## RESPONSE FORMAT
Return valid JSON only, no other text:
{{
  "concepts": [
    {{"name": "concept name", "category": "category", "description": "brief description"}}
  ],
  "relationships": [
    {{"from": "concept1", "to": "concept2", "type": "relationship_type"}}
  ]
}}
"""


class Concept(TypedDict):
    """Extracted concept."""

    name: str
    category: str
    description: str


class Relationship(TypedDict):
    """Extracted relationship between concepts."""

    from_concept: str  # 'from' is reserved in Python
    to_concept: str
    type: str


class ExtractionResult(TypedDict):
    """Result of concept extraction from a chunk."""

    concepts: list[Concept]
    relationships: list[Relationship]


def extract_concepts_from_chunk(
    text: str,
    max_retries: int = 3,
) -> ExtractionResult:
    """Extract concepts and relationships from a chunk of text.

    Args:
        text: Chunk text to analyze
        max_retries: Number of retry attempts for rate limits

    Returns:
        ExtractionResult with concepts and relationships

    Raises:
        RateLimitError: If rate limit exceeded after all retries
        APIError: If API call fails after retries
        json.JSONDecodeError: If response is not valid JSON
    """
    client = _get_client()
    prompt = EXTRACTION_PROMPT.format(text=text)

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )

            # Parse JSON response
            content = response.content[0].text
            result = json.loads(content)

            # Normalize the relationships key (from → from_concept)
            relationships: list[Relationship] = []
            for rel in result.get("relationships", []):
                relationships.append({
                    "from_concept": rel["from"],
                    "to_concept": rel["to"],
                    "type": rel["type"],
                })

            extraction: ExtractionResult = {
                "concepts": result.get("concepts", []),
                "relationships": relationships,
            }

            structured_logger.info(
                "concepts",
                "Extracted concepts from chunk",
                concept_count=len(extraction["concepts"]),
                relationship_count=len(extraction["relationships"]),
            )

            return extraction

        except RateLimitError:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                structured_logger.warning(
                    "concepts",
                    f"Rate limited, retrying in {wait}s",
                    attempt=attempt + 1,
                )
                time.sleep(wait)
            else:
                raise

        except APIError as e:
            if attempt < max_retries - 1:
                structured_logger.warning(
                    "concepts",
                    f"API error, retrying: {e}",
                    attempt=attempt + 1,
                )
                time.sleep(2)
            else:
                raise

        except json.JSONDecodeError as e:
            structured_logger.error(
                "concepts",
                f"Failed to parse JSON response: {e}",
                response_preview=content[:200] if "content" in dir() else "N/A",
            )
            raise

    # Should not reach here, but satisfy type checker
    return {"concepts": [], "relationships": []}


# Source-level relationship prompt
SOURCE_RELATIONSHIP_PROMPT = """These concepts all appear in the same book/document about data management.
Identify meaningful relationships between them.

## RELATIONSHIP TYPES
- enables: A makes B possible
- requires: A depends on B
- part_of: A is a component of B
- similar_to: A is conceptually similar to B
- contrasts: A is the opposite of B

## CONCEPTS FROM THIS SOURCE
{concepts_list}

## RULES
1. Only identify relationships that are meaningful and likely true
2. Don't force relationships - it's okay to return few or none
3. Focus on the most important/obvious relationships
4. Consider how these concepts would relate in data management context

## RESPONSE FORMAT
Return valid JSON array only:
[
  {{"from": "concept1", "to": "concept2", "type": "relationship_type"}}
]

If no clear relationships, return: []
"""


def find_source_relationships(
    concepts: list[dict],
    max_retries: int = 3,
) -> list[Relationship]:
    """Find relationships between concepts in the same source.

    Called after all chunks from a source have been processed.

    Args:
        concepts: List of concept dicts with name, category, description
        max_retries: Number of retry attempts

    Returns:
        List of relationships between concepts
    """
    if len(concepts) < 2:
        return []

    client = _get_client()

    # Format concepts for prompt
    concepts_list = "\n".join([
        f"- {c['name']} ({c['category']}): {c.get('description', 'No description')}"
        for c in concepts
    ])

    prompt = SOURCE_RELATIONSHIP_PROMPT.format(concepts_list=concepts_list)

    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=EXTRACTION_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text
            raw_relationships = json.loads(content)

            # Normalize to Relationship type
            relationships: list[Relationship] = []
            for rel in raw_relationships:
                relationships.append({
                    "from_concept": rel["from"],
                    "to_concept": rel["to"],
                    "type": rel["type"],
                })

            structured_logger.info(
                "concepts",
                "Found source-level relationships",
                relationship_count=len(relationships),
            )

            return relationships

        except RateLimitError:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) * 2
                time.sleep(wait)
            else:
                raise

        except APIError as e:
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                raise

        except json.JSONDecodeError:
            structured_logger.warning(
                "concepts",
                "Failed to parse source relationships JSON",
            )
            return []

    return []
