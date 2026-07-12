"""
Claude Code stream-json event parser.

When Claude Code runs with streaming output (the default for
headless workers), it emits newline-delimited JSON events.
This module extracts token usage, tool use events, and
final-text from the stream.
"""

import json
from typing import Iterator


def parse_stream_events(stream_lines: Iterator[str]) -> Iterator[dict]:
    """Parse newline-delimited JSON stream events.

    Yields parsed event dicts. Silently skips malformed lines.
    """
    for line in stream_lines:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def extract_token_usage(events: list[dict]) -> dict:
    """Extract cumulative token usage from stream events.

    Returns: {"tokens_in": int, "tokens_out": int}
    """
    for event in reversed(events):
        if event.get("type") == "result" and isinstance(event.get("usage"), dict):
            usage = event["usage"]
            return {
                "tokens_in": int(usage.get("input_tokens", 0)),
                "tokens_out": int(usage.get("output_tokens", 0)),
            }

    tokens_in = 0
    tokens_out = 0
    for event in events:
        message = event.get("message") or {}
        usage = event.get("usage") or message.get("usage") or {}
        tokens_in = max(tokens_in, usage.get("input_tokens", 0))
        tokens_out += usage.get("output_tokens", 0)
    return {"tokens_in": tokens_in, "tokens_out": tokens_out}


def extract_tool_use(events: list[dict]) -> list[dict]:
    """Extract tool-use events from stream.

    Returns list of {tool_name, tool_input} dicts.
    """
    tools = []
    for event in events:
        if event.get("type") == "tool_use":
            tools.append({
                "tool_name": event.get("name", "unknown"),
                "tool_input": event.get("input", {}),
            })
    return tools


def extract_final_text(events: list[dict]) -> str:
    """Extract the final text output from stream events.

    Looks for the last text block in the last assistant message.
    """
    for event in reversed(events):
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            return event["result"]

    last_text = ""
    for event in events:
        if event.get("type") == "text":
            last_text = event.get("text", "")
        elif event.get("type") == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                last_text += delta.get("text", "")
        elif event.get("type") == "assistant":
            message = event.get("message") or {}
            for block in message.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    last_text = block.get("text", "")
    return last_text


def count_turns(events: list[dict]) -> int:
    """Count the number of assistant turns in the stream."""
    for event in reversed(events):
        if event.get("type") == "result" and isinstance(event.get("num_turns"), int):
            return event["num_turns"]

    turns = 0
    for event in events:
        if event.get("type") in {"message_start", "assistant"}:
            turns += 1
    return max(turns, 1)
