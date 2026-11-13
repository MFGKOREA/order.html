"""Ask GPT one board question.

Credentials: OPENAI_API_KEY on the machine that runs this. In a Claude cloud environment, a
network secret saved for api.openai.com is injected by the proxy instead, so no variable is needed.
Model: GPT_MODEL, default gpt-5-mini.
"""
import os

from openai import OpenAI

MODEL = os.environ.get("GPT_MODEL", "gpt-5-mini")


def ask(question, system, timeout=8.0):
    # The placeholder only lets the SDK start; the cloud proxy replaces it with the saved key.
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", "proxy-injected"),
                    timeout=timeout, max_retries=0)
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": question}],
    )
    return (resp.choices[0].message.content or "").strip()
