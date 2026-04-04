"""MindRouter LLM client for Codenames AI.

OpenAI-compatible REST API via httpx. Adapted from marc2/models.py.
"""

import json
import os
import re
import time

import httpx
import yaml
from pathlib import Path


CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return yaml.safe_load(f)


def find_model(config, name):
    for m in config["models"]:
        if m["name"] == name:
            return m
    raise ValueError(f"Model '{name}' not found in config")


SPYMASTER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "codenames_clue",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "clue": {"type": "string"},
                "number": {"type": "integer"},
                "reasoning": {"type": "string"},
            },
            "required": ["clue", "number", "reasoning"],
            "additionalProperties": False,
        },
    },
}

GUESSER_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "codenames_guess",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "guess": {"type": "string"},
                "reasoning": {"type": "string"},
            },
            "required": ["guess", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def call_llm(model_config, messages, response_format=None):
    """Call an LLM. Returns (raw_response_text, parsed_content, latency_ms).

    If response_format is provided, it's passed to the API for structured output.
    """
    api_key = _get_api_key(model_config)
    endpoint = model_config["endpoint"].rstrip("/")
    url = f"{endpoint}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": model_config["model_id"],
        "messages": messages,
        "temperature": model_config.get("temperature", 0.7),
    }
    if "max_tokens" in model_config:
        body["max_tokens"] = model_config["max_tokens"]
    if response_format:
        body["response_format"] = response_format

    start = time.monotonic()
    with httpx.Client(timeout=model_config.get("timeout", 120.0)) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
    latency_ms = int((time.monotonic() - start) * 1000)

    raw = resp.text
    data = resp.json()
    msg = data["choices"][0]["message"]
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    if content:
        text = content
    elif reasoning:
        # Content is empty — try to find JSON in reasoning (some models
        # put their answer at the end of reasoning when they run out of tokens)
        extracted = parse_json_response(reasoning)
        if extracted:
            text = json.dumps(extracted)
        else:
            text = reasoning
    else:
        text = ""
    return raw, text, latency_ms


def parse_json_response(text):
    """Extract JSON object from LLM response text.

    Handles responses wrapped in markdown code fences or with surrounding text.
    """
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try extracting any JSON object
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _get_api_key(config):
    env_var = config.get("api_key_env")
    if not env_var:
        return None
    key = os.environ.get(env_var)
    if not key:
        raise RuntimeError(f"Environment variable {env_var} not set")
    return key
