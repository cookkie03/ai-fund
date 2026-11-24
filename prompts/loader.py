"""Loader module for agent system prompts with database versioning support."""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any

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
    "bridge": "bridge",
}


def normalize_agent_name(agent_name: str) -> str:
    normalized = agent_name.strip().lower()
    return "ticker_agent" if normalized.startswith("ticker:") else ROLE_ALIASES.get(normalized, normalized)


def load_prompt(agent_name: str, prompts_dir: Path | None = None, db: Any | None = None) -> tuple[str, str]:
    """Load system prompt markdown (from DB if available, else file) and calculate its SHA-256 hash.

    Returns:
        tuple[str, str]: (prompt_text, sha256_hash)
    """
    canonical_name = normalize_agent_name(agent_name)
    base_dir = prompts_dir or PROMPTS_DIR

    # Check DB first if db session is provided
    if db is not None and hasattr(db, "latest_prompt_version"):
        row = db.latest_prompt_version(canonical_name)
        if row is not None:
            text = row["text"]
            prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return text, prompt_hash

    # Fallback to file
    prompt_path = base_dir / f"{canonical_name}.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(
            f"Prompt file not found for agent '{agent_name}' at {prompt_path}"
        )

    text = prompt_path.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, prompt_hash


def load_prompt_full(agent_name: str, prompts_dir: Path | None = None, db: Any | None = None) -> tuple[str, str, int, bool]:
    canonical_name = normalize_agent_name(agent_name)
    base_dir = prompts_dir or PROMPTS_DIR

    if db is not None and hasattr(db, "latest_prompt_version"):
        row = db.latest_prompt_version(canonical_name)
        if row is not None:
            text = row["text"]
            prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            return text, prompt_hash, int(row["version"]), False

    prompt_path = base_dir / f"{canonical_name}.md"
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found for agent '{agent_name}' at {prompt_path}")

    text = prompt_path.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, prompt_hash, 0, True


def compute_prompt_diff(old_text: str, new_text: str) -> str:
    diff = list(difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile="current",
        tofile="proposed",
    ))
    return "".join(diff)
