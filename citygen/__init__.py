"""citygen: prompt-to-city layout generator (milestone M0: spec, presets, model schema).

Offline and deterministic. citygen makes no network calls and depends on no LLM SDK; the
prompt-to-spec step is done by a Claude Code session following `.claude/skills/citygen`.
"""

__version__ = "0.1.0"
