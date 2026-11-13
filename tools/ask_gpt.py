"""Ask GPT one board question, streaming the answer line by line.

Credentials: OPENAI_API_KEY on the machine that runs this. In a Claude cloud environment, a
network secret saved for api.openai.com is injected by the proxy instead, so no variable is needed.
Model: GPT_MODEL, default gpt-5-mini.
GPT_REASONING_EFFORT: default "minimal" (fastest for gpt-5-mini); set it empty to use the model default.
GPT_PRIORITY=1: OpenAI priority processing (faster, higher price).
"""
import json
import os

import httpx2  # the SDK's own HTTP library (installed with it)
from openai import DefaultHttpx2Client, OpenAI

MODEL = os.environ.get("GPT_MODEL", "gpt-5-mini")
REASONING_EFFORT = os.environ.get("GPT_REASONING_EFFORT", "minimal")
PRIORITY = os.environ.get("GPT_PRIORITY") == "1"
# Set by the hub for the cost meter: on_usage(model, input_tokens, output_tokens) after each answer.
on_usage = None

_client = None


def client():
    """One client per process, so its open connection is reused across questions."""
    global _client
    if _client is None:
        # The placeholder only lets the SDK start; the cloud proxy replaces it with the saved key.
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "proxy-injected"),
                         timeout=8.0, max_retries=0)
    return _client


def warm():
    """Get ready before the first question: load the SDK's streaming code offline, then open the
    connection (free endpoint, no tokens)."""
    _prime()
    client().models.list()


def _prime():
    """Push one canned answer through the SDK's stream parser without touching the network."""
    chunk = {"id": "prime", "object": "chat.completion.chunk", "created": 0, "model": MODEL,
             "choices": [{"index": 0, "delta": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}
    sse = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode()
    transport = httpx2.MockTransport(lambda request: httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse))
    offline = OpenAI(api_key="offline", base_url="http://offline.invalid/v1", max_retries=0,
                     http_client=DefaultHttpx2Client(transport=transport))
    for _ in _lines(offline, "prime", "prime"):
        pass


def lines(question, system):
    """Yield answer lines as they arrive. Closing the generator stops the request."""
    return _lines(client(), question, system)


def _lines(c, question, system):
    params = dict(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": question}],
        stream=True,
        stream_options={"include_usage": True},  # the last chunk reports tokens, for the cost meter
    )
    if REASONING_EFFORT:
        params["reasoning_effort"] = REASONING_EFFORT
    if PRIORITY:
        params["service_tier"] = "priority"
    stream = c.chat.completions.create(**params)
    buf = ""
    try:
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage and on_usage:
                on_usage(MODEL, usage.prompt_tokens, usage.completion_tokens)
            if not chunk.choices:
                continue
            buf += chunk.choices[0].delta.content or ""
            while "\n" in buf:
                line, buf = buf.split("\n", 1)
                yield line
        if buf:
            yield buf
    finally:
        stream.close()
