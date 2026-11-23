"""Loader module for agent system prompts."""

from __future__ import annotations

import hashlib
from pathlib import Path

# Directory holding prompt markdown files
PROMPTS_DIR = Path(__file__).resolve().parent

ROLE_ALIASES: dict[str, str] = {
    "pm": "portfolio_manager",
    "portfolio-manager": "portfolio_manager",
    "market": "market_analyst",
    "sentiment": "sentiment_analyst",
    "technical": "technical_analyst",
    "fundamental": "fundamental_analyst",
    "risk": "risk_analyst",
}


def load_prompt(agent_name: str, prompts_dir: Path | None = None) -> tuple[str, str]:
    """Load system prompt markdown and calculate its SHA-256 hash.

    Args:
        agent_name: Canonical role or agent name (e.g. 'portfolio_manager', 'technical_analyst')
        prompts_dir: Optional override directory path (defaults to prompts/)

    Returns:
        tuple[str, str]: (prompt_text, sha256_hash)

    Raises:
        FileNotFoundError: If no markdown prompt file exists for agent_name.
    """
    base_dir = prompts_dir or PROMPTS_DIR
    normalized = agent_name.strip().lower()
    canonical_name = ROLE_ALIASES.get(normalized, normalized)

    prompt_path = base_dir / f"{canonical_name}.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(
            f"Prompt file not found for agent '{agent_name}' at {prompt_path}"
        )

    text = prompt_path.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, prompt_hash
