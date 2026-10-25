"""Independent translation of Cairo messages to the FCC Messages HTTP contract."""

import copy
import json

from cairo.models.errors import ModelError


def encode(messages: list[dict], tools: list[dict]) -> dict:
    system, wire = [], []
    try:
        for message in messages:
            role, text = message["role"], message.get("content", "")
            if not isinstance(text, str):
                raise ValueError
            if role == "system":
                system.append(text)
                continue
            if role == "tool":
                role = "user"
                blocks = [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": text,
                    }
                ]
            elif role in {"assistant", "user"}:
                state = message.get("_provider_state", {})
                if role == "assistant" and state.get("format") == "fcc-messages":
                    blocks = copy.deepcopy(state["content"])
                else:
                    blocks = [{"type": "text", "text": text}] if text else []
                    for call in message.get("tool_calls", []):
                        function = call["function"]
                        arguments = function["arguments"]
                        if isinstance(arguments, str):
                            arguments = json.loads(arguments)
                        if not isinstance(arguments, dict) or role != "assistant":
                            raise ValueError
                        blocks.append(
                            {
                                "type": "tool_use",
                                "id": call["id"],
                                "name": function["name"],
                                "input": arguments,
                            }
                        )
            else:
                raise ValueError
            if not blocks:
                raise ValueError
            if wire and wire[-1]["role"] == role:
                wire[-1]["content"].extend(blocks)
            else:
                wire.append({"role": role, "content": blocks})
        if not wire:
            raise ValueError
        body = {"messages": wire, "stream": False}
        if system:
            body["system"] = "\n\n".join(system)
        if tools:
            body["tools"] = [
                {
                    "name": t["function"]["name"],
                    "description": t["function"].get("description", ""),
                    "input_schema": copy.deepcopy(t["function"]["parameters"]),
                }
                for t in tools
            ]
        return body
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ModelError(
            "Conversa ou ferramentas em formato inválido.", code="invalid_request"
        ) from None


def decode(data: dict):
    from cairo.models import Reply

    try:
        if data.get("type") != "message" or data.get("role") != "assistant":
            raise ValueError
        if data.get("stop_reason") == "max_tokens":
            raise ModelError(
                "FCC atingiu o limite de saída; ajuste CAIRO_MAX_OUTPUT_TOKENS.",
                code="output_limit",
            )
        blocks = data["content"]
        if not isinstance(blocks, list):
            raise ValueError
        text, calls, ids = [], [], set()
        for block in blocks:
            kind = block["type"]
            if kind == "text":
                if not isinstance(block["text"], str):
                    raise ValueError
                text.append(block["text"])
            elif kind == "tool_use":
                if (
                    not all(
                        isinstance(block[k], str) and block[k] for k in ("id", "name")
                    )
                    or not isinstance(block["input"], dict)
                    or block["id"] in ids
                ):
                    raise ValueError
                ids.add(block["id"])
                calls.append(
                    {
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(
                                block["input"], ensure_ascii=False, allow_nan=False
                            ),
                        },
                    }
                )
            elif kind not in {"thinking", "redacted_thinking"}:
                raise ValueError
        if len(calls) > 8 or (not "".join(text).strip() and not calls):
            raise ValueError
        # Opaque protocol state stays within this invocation's tool loop, not memory/logs.
        return Reply(
            "\n".join(text),
            calls,
            {"format": "fcc-messages", "content": copy.deepcopy(blocks)},
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ModelError(
            "FCC retornou uma resposta inesperada de mensagens/ferramentas.",
            code="unexpected_response",
        ) from None
