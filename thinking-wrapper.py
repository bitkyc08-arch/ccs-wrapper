#!/usr/bin/env python3
"""
thinking-wrapper.py — SSE Streaming + Thinking + Codex Effort 변환 프록시

지원하는 변환:
1. Claude Thinking 모델: OpenAI → Anthropic Messages + thinking → SSE 변환 응답
2. Codex Effort 모델: effort 접미사 파싱 → Codex Provider SSE passthrough
3. 나머지 모델: CCS SSE passthrough

Usage:
    python3 thinking-wrapper.py [--port 8318]
"""

import json
import time
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn
import argparse
import re

app = FastAPI(title="CCS Thinking + Effort Wrapper")

CCS_BASE = "http://localhost:8317"
CCS_API_KEY = "ccs-internal-managed"

# Claude thinking 모델: Anthropic Messages로 변환
THINKING_MODELS = {
    "claude-opus-4-6-thinking":   {"effort": "high", "max_tokens": 128000},
    "claude-sonnet-4-5-thinking": {"effort": "medium", "max_tokens": 64000},
}

# Codex effort 접미사 패턴
EFFORT_SUFFIXES = re.compile(r"^(.+)-(xhigh|high|medium|low)$")

# effort 매핑
EFFORT_MAP = {
    "low": "low", "medium": "medium", "high": "high",
    "max": "max", "xhigh": "xhigh",
}

CCS_HEADERS = {
    "Authorization": f"Bearer {CCS_API_KEY}",
    "Content-Type": "application/json",
}


@app.get("/v1/models")
async def list_models():
    """CCS의 모델 목록을 그대로 전달"""
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            f"{CCS_BASE}/v1/models",
            headers={"Authorization": f"Bearer {CCS_API_KEY}"},
        )
        return JSONResponse(content=r.json(), status_code=r.status_code)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    model = body.get("model", "")
    is_stream = body.get("stream", False)

    print(f"📨 {model} stream={is_stream} msgs={len(body.get('messages',[]))} tools={len(body.get('tools',[]))}")

    # --- Route 1: Claude Thinking 모델 ---
    if model in THINKING_MODELS:
        return await _handle_thinking(body, model, is_stream)

    # --- Route 2: Codex Effort 접미사 모델 ---
    match = EFFORT_SUFFIXES.match(model)
    if match:
        base_model = match.group(1)
        effort = match.group(2)
        return await _handle_codex_effort(body, base_model, effort)

    # --- Route 3: 일반 모델 passthrough (SSE stream) ---
    return await _stream_passthrough(f"{CCS_BASE}/v1/chat/completions", body)


async def _stream_passthrough(url: str, body: dict):
    """CCS의 SSE 스트리밍 응답을 그대로 Copilot에 전달"""
    body["stream"] = True  # CCS에 스트리밍 강제

    async def generate():
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST", url, json=body, headers=CCS_HEADERS,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        yield line + "\n"
                    else:
                        yield "\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _handle_codex_effort(body: dict, base_model: str, effort: str):
    """Codex effort 모델: 접미사 파싱 → reasoning_effort 삽입 → SSE passthrough"""
    body["model"] = base_model
    body["reasoning_effort"] = effort

    # VS Code Copilot이 보내는 불필요한 필드 제거
    for key in ["n", "logprobs", "top_logprobs", "response_format"]:
        body.pop(key, None)

    print(f"🔧 Codex effort: {base_model} + {effort}")
    return await _stream_passthrough(
        f"{CCS_BASE}/api/provider/codex/v1/chat/completions", body
    )


async def _handle_thinking(body: dict, model: str, is_stream: bool):
    """Claude thinking 모델: Anthropic Messages → OpenAI SSE 변환"""
    config = THINKING_MODELS[model]

    reasoning_effort = body.get("reasoning_effort", None)
    effort = EFFORT_MAP.get(reasoning_effort, config["effort"])

    messages = body.get("messages", [])
    anthropic_messages = []
    system_content = None

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # content가 list인 경우 (multimodal) → text만 추출
        if isinstance(content, list):
            text_parts = [p.get("text", "") for p in content if p.get("type") == "text"]
            content = "\n".join(text_parts) if text_parts else str(content)

        if role == "system":
            system_content = content if isinstance(content, str) else str(content)

        elif role == "assistant":
            # assistant + tool_calls → Anthropic content blocks
            tool_calls_data = msg.get("tool_calls", [])
            if tool_calls_data:
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in tool_calls_data:
                    func = tc.get("function", {})
                    try:
                        input_data = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        input_data = {"raw": func.get("arguments", "")}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", f"call_{int(time.time())}"),
                        "name": func.get("name", ""),
                        "input": input_data,
                    })
                anthropic_messages.append({"role": "assistant", "content": blocks})
            else:
                anthropic_messages.append({"role": "assistant", "content": content})

        elif role == "tool":
            # tool result → Anthropic tool_result content block (user role)
            tool_call_id = msg.get("tool_call_id", "")
            result_content = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
            tool_result_block = {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                "content": result_content,
            }
            # 이전 메시지가 user이고 content가 list면 합침
            if anthropic_messages and anthropic_messages[-1]["role"] == "user" and isinstance(anthropic_messages[-1]["content"], list):
                anthropic_messages[-1]["content"].append(tool_result_block)
            else:
                anthropic_messages.append({"role": "user", "content": [tool_result_block]})

        elif role == "user":
            anthropic_messages.append({"role": "user", "content": content})

    if not anthropic_messages:
        anthropic_messages = [{"role": "user", "content": "Hello"}]

    # Anthropic: user/assistant 교대 필수 → 연속 같은 role 합침
    merged = []
    for msg in anthropic_messages:
        if merged and merged[-1]["role"] == msg["role"]:
            prev = merged[-1]["content"]
            curr = msg["content"]
            # 둘 다 string이면 합침
            if isinstance(prev, str) and isinstance(curr, str):
                merged[-1]["content"] = prev + "\n\n" + curr
            # 둘 다 list면 extend
            elif isinstance(prev, list) and isinstance(curr, list):
                prev.extend(curr)
            # 하나가 string, 하나가 list → list로 통합
            elif isinstance(prev, str) and isinstance(curr, list):
                merged[-1]["content"] = [{"type": "text", "text": prev}] + curr
            elif isinstance(prev, list) and isinstance(curr, str):
                prev.append({"type": "text", "text": curr})
        else:
            merged.append(dict(msg))
    anthropic_messages = merged

    max_tokens = (
        body.get("max_tokens")
        or body.get("max_completion_tokens")
        or config["max_tokens"]
    )
    # Antigravity 200K context cap → max_tokens 제한
    max_tokens = min(max_tokens, 16000)

    anthropic_body = {
        "model": model,
        "max_tokens": max_tokens,
        "thinking": {"type": "adaptive", "effort": effort},
        "messages": anthropic_messages,
    }
    if system_content:
        anthropic_body["system"] = system_content

    # tools 변환: OpenAI format → Anthropic format (최대 64개, 초과 시 잘라냄)
    openai_tools = body.get("tools", [])
    if openai_tools:
        anthropic_tools = []
        for t in openai_tools:
            if t.get("type") == "function":
                func = t.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name", ""),
                    "description": func.get("description", "")[:1024],
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                })
        if anthropic_tools:
            anthropic_body["tools"] = anthropic_tools
            print(f"   🔧 Tools: {len(anthropic_tools)} forwarded")

    print(f"🔍 Thinking: model={model}, effort={effort}, msgs={len(anthropic_messages)}, stream={is_stream}")

    try:
        async with httpx.AsyncClient(timeout=300) as client:
            r = await client.post(
                f"{CCS_BASE}/v1/messages",
                json=anthropic_body,
                headers={
                    **CCS_HEADERS,
                    "anthropic-version": "2023-06-01",
                },
            )
    except Exception as e:
        print(f"⚠️ Thinking error: {e}")
        return JSONResponse(
            content={"error": {"message": str(e), "type": "proxy_error"}},
            status_code=502,
        )

    if r.status_code != 200:
        print(f"⚠️ Thinking upstream {r.status_code}: {r.text[:200]}")
        return JSONResponse(
            content={"error": {"message": f"Upstream: {r.text}", "type": "proxy_error"}},
            status_code=r.status_code,
        )

    result = r.json()

    # Anthropic response → thinking + text + tool_use 분리
    reasoning_content = None
    text_content = ""
    tool_calls = []

    for block in result.get("content", []):
        if block.get("type") == "thinking":
            reasoning_content = block.get("thinking", "")
        elif block.get("type") == "text":
            raw_text = block.get("text", "")
            thinking_match = re.search(r'<thinking>(.*?)</thinking>', raw_text, re.DOTALL)
            if thinking_match:
                reasoning_content = thinking_match.group(1).strip()
                text_content += re.sub(r'<thinking>.*?</thinking>\s*', '', raw_text, flags=re.DOTALL).strip()
            else:
                text_content += raw_text
        elif block.get("type") == "tool_use":
            tool_calls.append({
                "id": block.get("id", f"call_{int(time.time())}"),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                },
            })

    if not text_content and not reasoning_content and not tool_calls:
        text_content = "(No content returned)"

    # finish_reason: tool call이 있으면 tool_calls, 아니면 stop
    finish_reason = "tool_calls" if tool_calls else "stop"

    completion_id = result.get("id", f"chatcmpl-{int(time.time())}")

    if is_stream:
        # SSE 스트리밍 포맷으로 응답
        return StreamingResponse(
            _thinking_to_sse(completion_id, model, text_content, reasoning_content, tool_calls, finish_reason),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # 일반 JSON 응답
        msg = {"role": "assistant", "content": text_content}
        if reasoning_content:
            msg["reasoning_content"] = reasoning_content
        if tool_calls:
            msg["tool_calls"] = tool_calls

        return JSONResponse(content={
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": msg,
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": result.get("usage", {}).get("input_tokens", 0),
                "completion_tokens": result.get("usage", {}).get("output_tokens", 0),
                "total_tokens": (
                    result.get("usage", {}).get("input_tokens", 0)
                    + result.get("usage", {}).get("output_tokens", 0)
                ),
            },
        })


async def _thinking_to_sse(completion_id: str, model: str, text: str, reasoning: str | None,
                           tool_calls: list | None = None, finish_reason: str = "stop"):
    """Anthropic 응답을 OpenAI SSE chat.completion.chunk 포맷으로 변환"""
    created = int(time.time())

    def chunk(delta: dict, fr=None):
        return "data: " + json.dumps({
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": fr,
            }],
        }, ensure_ascii=False) + "\n\n"

    # 1. role chunk
    yield chunk({"role": "assistant", "content": ""})

    # 2. content를 작은 조각으로 스트리밍
    if text:
        chunk_size = 20
        for i in range(0, len(text), chunk_size):
            yield chunk({"content": text[i:i + chunk_size]})

    # 3. tool_calls 스트리밍 (있을 경우)
    if tool_calls:
        for idx, tc in enumerate(tool_calls):
            # 첫 chunk: tool call 시작
            yield chunk({"tool_calls": [{
                "index": idx,
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["function"]["name"], "arguments": ""},
            }]})
            # arguments를 조각으로 전송
            args = tc["function"]["arguments"]
            args_chunk_size = 50
            for i in range(0, len(args), args_chunk_size):
                yield chunk({"tool_calls": [{
                    "index": idx,
                    "function": {"arguments": args[i:i + args_chunk_size]},
                }]})

    # 4. finish
    yield chunk({}, fr=finish_reason)

    # 5. done
    yield "data: [DONE]\n\n"


@app.get("/health")
async def health():
    return {"status": "ok", "backend": CCS_BASE, "routes": ["thinking+sse", "codex-effort+sse", "passthrough+sse"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CCS Wrapper (SSE Streaming)")
    parser.add_argument("--port", type=int, default=8318)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    print(f"🧠 CCS Wrapper Proxy (SSE) starting on {args.host}:{args.port}")
    print(f"   Backend: {CCS_BASE}")
    print(f"   Claude thinking: {list(THINKING_MODELS.keys())}")
    print(f"   Codex effort: regex {EFFORT_SUFFIXES.pattern}")
    print(f"   All routes: SSE streaming")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
