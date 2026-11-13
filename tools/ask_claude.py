"""Ask Claude one board question, streaming the answer line by line.

Credentials: ANTHROPIC_API_KEY (or an `ant auth login` profile) on the machine that runs this.
Model: CLAUDE_MODEL, default claude-opus-5-5.
CLAUDE_FAST=1: Claude fast mode (up to 2.5x output speed, 2x price; Opus 5.5 / Opus 5 / Opus 4.8 only).
"""
import json
import os

import anthropic
import httpx2  # the SDK's own HTTP library (installed with it)

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
FAST = os.environ.get("CLAUDE_FAST") == "1"
# Models that accept server-side refusal fallbacks (fallbacks="default").
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
FAST_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-opus-4-8"}
# Set by the hub for the cost meter: on_usage(model, input_tokens, output_tokens) after each answer
# (the model name ends in ":fast" for fast-mode answers, which cost double).
on_usage = None

_client = None


def client():
    """One client per process, so its open connection is reused across questions."""
    global _client
    if _client is None:
        _client = anthropic.Anthropic(timeout=8.0, max_retries=0)
    return _client


def warm():
    """Get ready before the first question: build the SDK's stream models offline, then open the
    connection (free endpoint, no tokens)."""
    _prime()
    client().models.list(limit=1)


def _prime():
    """Push one canned answer through the SDK's stream parser without touching the network.

    The SDK builds its response models on first use (~190 ms measured), which would otherwise land
    on the first real question.
    """
    events = [
        {"type": "message_start", "message": {
            "id": "msg_prime", "type": "message", "role": "assistant", "model": MODEL, "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 0, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "ok"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
         "usage": {"output_tokens": 1}},
        {"type": "message_stop"},
    ]
    sse = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()
    transport = httpx2.MockTransport(lambda request: httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse))
    offline = anthropic.Anthropic(api_key="offline", base_url="http://offline.invalid", max_retries=0,
                                  http_client=anthropic.DefaultHttpxClient(transport=transport))
    with offline.beta.messages.stream(**_params("prime", "prime", FAST and MODEL in FAST_MODELS)) as stream:
        for _ in stream.text_stream:
            pass
        stream.get_final_message()


def _params(question, system, fast):
    params = dict(
        model=MODEL,
        max_tokens=4096,
        system=system,
        output_config={"effort": "low"},  # short factual answers; least thinking before the first token
        messages=[{"role": "user", "content": question}],
    )
    betas = []
    if MODEL in FALLBACK_MODELS:
        betas.append("server-side-fallback-2026-07-01")
        params["fallbacks"] = "default"
    if fast:
        betas.append("fast-mode-2026-02-01")
        params["speed"] = "fast"
    if betas:
        params["betas"] = betas
    return params


def _stream(question, system, fast):
    buf = ""
    with client().beta.messages.stream(**_params(question, system, fast)) as stream:
        for text in stream.text_stream:
            buf += text
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                yield line
        if buf:
            yield buf
        final = stream.get_final_message()
    if on_usage and final.usage:
        on_usage(MODEL + (":fast" if fast else ""), final.usage.input_tokens, final.usage.output_tokens)
    # A mid-stream decline continues on the fallback model inside the same stream; only a refusal
    # of the whole chain ends here, and the caller then discards the partial answer.
    if final.stop_reason == "refusal":
        category = final.stop_details.category if final.stop_details else None
        raise RuntimeError(f"Claude declined (category: {category})")


def lines(question, system):
    """Yield answer lines as they arrive. Closing the generator stops the request."""
    fast = FAST and MODEL in FAST_MODELS
    started = False
    gen = _stream(question, system, fast)
    try:
        for line in gen:
            started = True
            yield line
        return
    except (anthropic.RateLimitError, anthropic.BadRequestError):
        if not fast or started:
            raise
    finally:
        gen.close()
    # Fast-mode pool busy (429) or fast mode not accepted (400): retry once at standard speed.
    yield from _stream(question, system, False)
