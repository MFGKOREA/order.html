"""Ask Claude one board question.

Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile) on the machine that runs this.
Model: CLAUDE_MODEL, default claude-opus-5-5.
"""
import os

import anthropic

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
# Models that accept server-side refusal fallbacks (fallbacks="default").
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


def ask(question, system, timeout=8.0):
    client = anthropic.Anthropic(timeout=timeout, max_retries=0)
    kwargs = dict(
        model=MODEL,
        max_tokens=4096,
        system=system,
        output_config={"effort": "low"},  # short factual answers; keeps latency down
        messages=[{"role": "user", "content": question}],
    )
    if MODEL in FALLBACK_MODELS:
        kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    resp = client.beta.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        category = resp.stop_details.category if resp.stop_details else None
        raise RuntimeError(f"Claude declined (category: {category})")
    return "".join(b.text for b in resp.content if b.type == "text").strip()
