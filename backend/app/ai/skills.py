"""Load packaged marketing Agent Skills as expert guidance for AI generations.

The agents feed the relevant skill's instructions into the OpenAI system prompt
so the generated copy follows the same frameworks as the Claude Code skills.
Core skills are packaged under ``app/skills_data/`` so they ship inside the
backend image (works locally and in the cloud). Full skill set lives in
``.claude/skills/`` for Claude Code itself.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

# Packaged skills shipped with the backend image.
_PACKAGED = Path(__file__).resolve().parent.parent / "skills_data"
# Optional override / fuller set (e.g. a mounted .claude/skills).
_OVERRIDE = os.environ.get("SKILLS_DIR")

# Keep per-skill injected text bounded so prompt cost stays reasonable.
_MAX_CHARS = 4000


def _strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


@functools.lru_cache(maxsize=64)
def load_skill(name: str) -> str:
    for base in (_OVERRIDE, _PACKAGED):
        if not base:
            continue
        p = Path(base) / name / "SKILL.md"
        if p.exists():
            return _strip_frontmatter(p.read_text(encoding="utf-8", errors="ignore"))[:_MAX_CHARS]
    return ""


def system_prompt(*names: str,
                  base: str = "You are an expert B2B marketing and sales operator. "
                              "Apply the frameworks below. Respond ONLY with valid JSON.") -> str:
    """Build a system prompt that injects the named skills' guidance."""
    chunks = [base]
    for n in names:
        s = load_skill(n)
        if s:
            chunks.append(f"\n\n## Skill: {n}\n{s}")
    return "\n".join(chunks)
