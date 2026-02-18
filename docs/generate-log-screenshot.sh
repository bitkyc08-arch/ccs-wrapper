#!/bin/bash
# 로그 스크린샷 생성용 (silicon 또는 carbon 사용 시)
# 이 파일은 README용 로그 예시 텍스트
cat << 'LOG'
📨 [messages] claude-sonnet-4-5-20250929 → gpt-5.3-codex-xhigh stream=True msgs=5
🔧 [messages] Codex effort: gpt-5.3-codex + xhigh, stream=True
INFO:     127.0.0.1:55457 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
📨 [messages] claude-sonnet-4-5-20250929 → gpt-5.3-codex-xhigh stream=True msgs=5
🔧 [messages] Codex effort: gpt-5.3-codex + xhigh, stream=True
INFO:     127.0.0.1:55468 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
📨 [messages] claude-haiku-4-5-20251001 → claude-sonnet-4-6 stream=True msgs=1
INFO:     127.0.0.1:55476 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
📨 [messages] claude-opus-4-6 stream=True msgs=1
INFO:     127.0.0.1:55477 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
📨 [messages] claude-sonnet-4-5-20250929 → gpt-5.3-codex-xhigh stream=True msgs=9
🔧 [messages] Codex effort: gpt-5.3-codex + xhigh, stream=True
INFO:     127.0.0.1:55481 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
LOG
