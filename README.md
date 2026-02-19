# CCS Thinking Wrapper

[CCS(Claude Code Switch)](https://github.com/kaitranntt/ccs) 위에 얹는 프록시 래퍼. Claude Code CLI와 VS Code Copilot BYOK가 thinking/effort 모델을 투명하게 사용할 수 있게 해준다.

## 왜 필요한가

CCS(`localhost:8317`)는 여러 AI 프로바이더(Antigravity, Codex, Copilot)를 하나의 엔드포인트로 통합하지만, 두 가지 한계가 있다:

1. **Codex effort 접미사**(`-xhigh`, `-high` 등)가 CCS 일반 라우터에서 `unknown provider` 에러
2. **Claude thinking 파라미터**를 OpenAI 형식 클라이언트(VS Code Copilot)가 전달할 수 없음

이 래퍼(`localhost:8318`)가 모델명을 보고 자동으로 적절한 CCS 엔드포인트로 라우팅한다.

## 아키텍처

```mermaid
flowchart LR
    subgraph Clients
        CC["Claude Code CLI"]
        CP["VS Code Copilot"]
    end

    subgraph "Wrapper :8318"
        M["/v1/messages"]
        C["/v1/chat/completions"]
        A{"모델명 분석"}
        R1["Route 1: Thinking"]
        R2["Route 2: Codex Effort"]
        R3["Route 3: Passthrough"]
    end

    subgraph "CCS :8317"
        AGY["Antigravity"]
        CDX["Codex"]
        GH["Copilot"]
        GM["Gemini"]
    end

    CC -->|Anthropic| M
    CP -->|OpenAI| C
    M --> A
    C --> A
    A -->|"claude-*-thinking"| R1
    A -->|"*-xhigh, *-high..."| R2
    A -->|"기타"| R3
    R1 -->|"thinking 삽입"| AGY
    R2 -->|"reasoning_effort"| CDX
    R3 --> AGY
    R3 --> GH
    R3 --> GM
```

### 모델 별칭 (리맵)

Claude Code가 내부적으로 Opus/Sonnet/Haiku 3-tier 슬롯을 자동 선택하는데, 래퍼가 이 슬롯을 원하는 모델로 리맵한다:

```mermaid
flowchart LR
    subgraph "Claude Code 슬롯"
        O["Opus\nclaude-opus-4-6-thinking"]
        S["Sonnet (기본)\nclaude-sonnet-4-5"]
        H["Haiku (경량)\nclaude-haiku-4-5"]
    end

    subgraph "래퍼 리맵"
        O -->|그대로| OT["claude-opus-4-6-thinking\n🧠 thinking max"]
        S -->|"리맵"| SX["gpt-5.3-codex-xhigh\n⚡ Codex xhigh"]
        H -->|"리맵"| HM["gpt-5-mini\n🚀 GPT-5 Mini"]
    end

    style SX fill:#2d5a27,stroke:#4ade80,color:#fff
    style HM fill:#1e3a5f,stroke:#60a5fa,color:#fff
    style OT fill:#5a2d27,stroke:#f87171,color:#fff
```

이 별칭은 `thinking-wrapper.py` 상단의 `MODEL_ALIASES` dict에서 수정 가능.

---

## 사전 준비: CCS 설치 및 실행

래퍼는 CCS 뒤에서 동작하므로 CCS가 먼저 실행 중이어야 한다.

### 1. CCS 설치

- GitHub: https://github.com/kaitranntt/ccs
- npm: https://www.npmjs.com/package/@kaitranntt/ccs

```bash
# npm으로 글로벌 설치
npm install -g @kaitranntt/ccs

# 또는 yarn/pnpm/bun
yarn global add @kaitranntt/ccs
pnpm add -g @kaitranntt/ccs
bun add -g @kaitranntt/ccs
```

### 2. OAuth 프로바이더 등록

CCS는 여러 AI 프로바이더의 OAuth를 원클릭으로 연결한다. 최초 실행 시 브라우저가 열리며 인증 후 토큰이 `~/.ccs/cliproxy/auth/`에 저장된다.

#### 방법 A: 웹 대시보드 (가장 쉬움) ⭐

```bash
ccs config
```

브라우저에서 CCS 대시보드가 열린다. GUI에서 프로바이더별 **Connect** 버튼을 눌러 OAuth 인증하면 끝. 모델 선택, thinking 설정, 계정 관리도 대시보드에서 가능하다.

#### 방법 B: CLI 개별 등록

```bash
# Antigravity (Claude/Gemini 모델) — Google 계정 인증
ccs agy --auth

# Codex (GPT-5.3 Codex) — ChatGPT 계정 인증 ⭐ 래퍼에 필수
ccs codex --auth

# GitHub Copilot (grok, gemini-2.5-pro 등 21종) — GitHub 계정 인증
ccs ghcp --auth

# Gemini (gemini-2.5-pro, 3-pro) — Google 계정 인증
ccs gemini --auth

# Kiro (AWS CodeWhisperer Claude) — AWS 계정 인증
ccs kiro --auth
```

**추가 계정 등록** (멀티 계정 지원):

```bash
ccs codex --auth --add          # Codex에 두 번째 계정 추가
ccs agy --accounts              # 등록된 계정 목록 확인
ccs codex --use <name>          # 특정 계정으로 전환
```

**SSH/원격 서버에서 인증** (브라우저 없이):

```bash
ccs codex --auth --headless     # URL이 출력됨 → 다른 기기에서 열어서 인증
```

> [!IMPORTANT]
> **래퍼에서 Codex effort 모델을 쓸려면 `ccs codex --auth`가 반드시 필요하다.** Antigravity(`ccs agy`)만 연결하면 Claude/Gemini만 사용 가능하고 Codex 모델은 502 에러가 남.

등록 후 확인:

```bash
# 프로바이더별 모델 확인
curl -s http://localhost:8317/v1/models \
  -H "Authorization: Bearer ccs-internal-managed" \
  | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin).get('data',[])]"
```

| 프로바이더 | OAuth 소스       | 주요 모델                                        |
| ---------- | ---------------- | ------------------------------------------------ |
| **agy**    | Google           | claude-opus-4-6, claude-sonnet-4-6, gemini-3-pro |
| **codex**  | ChatGPT (OpenAI) | gpt-5.3-codex, gpt-5.3-codex-spark               |
| **ghcp**   | GitHub           | grok-code-fast-1, gemini-2.5-pro, gpt-4.1        |
| **gemini** | Google           | gemini-2.5-pro, gemini-3-pro                     |
| **kiro**   | AWS              | Claude models via CodeWhisperer                  |

### 3. CCS 실행

CCS는 `localhost:8317`에서 CLIProxy 서버를 실행한다:

```bash
# 수동 실행
ccs start

# 또는 LaunchAgent로 자동 시작 등록
cat > ~/Library/LaunchAgents/com.ccs.cliproxy.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ccs.cliproxy</string>
    <key>ProgramArguments</key>
    <array>
        <string>ccs</string>
        <string>start</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF
launchctl load ~/Library/LaunchAgents/com.ccs.cliproxy.plist
```

### 4. CCS 동작 확인

```bash
# 모델 목록 확인
curl -s http://localhost:8317/v1/models \
  -H "Authorization: Bearer ccs-internal-managed" | python3 -m json.tool

# 간단한 테스트
curl -s http://localhost:8317/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ccs-internal-managed" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-sonnet-4-5","max_tokens":100,"messages":[{"role":"user","content":"hi"}]}'
```

CCS가 응답하면 래퍼 설치로 진행.

---

## 래퍼 설치

### 1. 저장소 클론

```bash
git clone https://github.com/bitkyc08-arch/ccs-wrapper.git
cd ccs-wrapper
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
# 또는 직접
pip install fastapi uvicorn httpx
```

### 3. 실행 테스트

```bash
python3 thinking-wrapper.py --port 8318
curl http://localhost:8318/health
```

### 4. 백그라운드 서비스 등록 (macOS launchd)

```bash
cat > ~/Library/LaunchAgents/com.ccs.thinking-wrapper.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ccs.thinking-wrapper</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/path/to/thinking-wrapper.py</string>  <!-- 실제 경로로 변경 -->
        <string>--port</string>
        <string>8318</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/ccs-wrapper-stdout.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/ccs-wrapper-stderr.log</string>

    <key>WorkingDirectory</key>
    <string>/path/to/ccs-wrapper</string>  <!-- 실제 경로로 변경 -->

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

# 등록 및 시작
launchctl load ~/Library/LaunchAgents/com.ccs.thinking-wrapper.plist

# 상태 확인
launchctl list | grep thinking-wrapper

# 재시작
launchctl stop com.ccs.thinking-wrapper && launchctl start com.ccs.thinking-wrapper

# 제거
launchctl unload ~/Library/LaunchAgents/com.ccs.thinking-wrapper.plist
```

---

## 클라이언트 연결

### Claude Code CLI

#### Step 1: 환경변수 설정

`.zshrc` (또는 `.bashrc`)에 추가:

```bash
# Claude Code → Wrapper(:8318) 경유
export ANTHROPIC_BASE_URL="http://localhost:8318"
export ANTHROPIC_AUTH_TOKEN="ccs-internal-managed"

# 기존 API 키가 있으면 반드시 삭제!
# export ANTHROPIC_API_KEY="sk-..."  ← 이거 있으면 삭제

# 모델별 alias (선택)
alias claude-opus='claude --model claude-opus-4-6-thinking'
alias claude-codex='claude --model gpt-5.3-codex-xhigh'
alias claude-sonnet='claude --model claude-sonnet-4-5'
```

#### Step 2: Auth conflict 해결

래퍼는 `ANTHROPIC_AUTH_TOKEN`으로 인증하는데, Claude Code에 기존 API 키가 저장되어 있으면 충돌한다:

```
⚠Auth conflict: Both a token (ANTHROPIC_AUTH_TOKEN) and an API key (ANTHROPIC_API_KEY) are set.
```

**해결 순서:**

```bash
# 1. .zshrc에서 ANTHROPIC_API_KEY 라인 삭제/주석처리
#    ANTHROPIC_AUTH_TOKEN만 남겨야 함

# 2. Claude Code 내부 저장 API 키 삭제
claude /logout

# 3. 온보딩 스킵 (최초 설치 시 로그인 프롬프트 건너뛰기)
#    ~/.claude.json 에 다음 추가:
cat > ~/.claude.json << 'EOF'
{
  "hasCompletedOnboarding": true
}
EOF

# 4. 새 터미널 열고 확인
claude
```

> [!TIP]
> `claude /logout` 후 다시 실행하면 "API key?" 프롬프트가 나올 수 있다. **No**를 선택하면 `ANTHROPIC_AUTH_TOKEN`만 사용하게 된다.

#### Step 3: settings.json 설정 (선택)

`~/.claude/settings.json`에서 기본 모델과 thinking을 설정할 수 있다:

```json
{
  "model": "opus",
  "alwaysThinkingEnabled": true
}
```

> [!NOTE]
> `"model": "opus"`로 설정하면 Claude Code가 Opus 슬롯(`claude-opus-4-6-thinking`)을 사용하고, 래퍼가 thinking max를 자동 삽입한다. 기본값(`sonnet`)이면 Codex xhigh로 리맵된다.

이후 그냥 `claude`만 실행하면 기본 Sonnet 슬롯이 자동으로 Codex xhigh로 리맵된다.

### VS Code Copilot BYOK

`chatLanguageModels.json`에서 thinking/effort 모델의 URL을 `:8318`로 지정:

```json
{
  "models": [
    {
      "id": "gpt-5.3-codex-xhigh",
      "url": "http://localhost:8318/v1",
      "vendor": "openai"
    },
    {
      "id": "claude-opus-4-6-thinking",
      "url": "http://localhost:8318/v1",
      "vendor": "openai"
    }
  ]
}
```

---

## 실행 순서 요약

```
1. CCS 시작        →  localhost:8317  (ccs start 또는 launchd)
2. Wrapper 시작    →  localhost:8318  (python3 thinking-wrapper.py 또는 launchd)
3. 클라이언트 연결 →  ANTHROPIC_BASE_URL=http://localhost:8318
4. claude 실행     →  기본 Sonnet이 Codex xhigh로 자동 리맵!
```

---

## 커스터마이징

### 모델 별칭 변경

`thinking-wrapper.py` 상단의 `MODEL_ALIASES` dict를 수정:

```python
MODEL_ALIASES = {
    "claude-haiku-4-5-20251001": "gpt-5-mini",             # Haiku → ?
    "claude-sonnet-4-5-20250929": "gpt-5.3-codex-xhigh",   # Sonnet → ?
}
```

### Thinking effort 기본값 변경

```python
THINKING_MODELS = {
    "claude-opus-4-6-thinking":   {"effort": "max", ...},   # max/high/medium/low
    "claude-sonnet-4-5-thinking": {"effort": "high", ...},
}
```

### CCS 백엔드 포트 변경

```python
CCS_BASE = "http://localhost:8317"  # 기본값. CCS 포트가 다르면 수정
```

---

## 로그 확인

```bash
# LaunchAgent stdout 로그
tail -f /tmp/ccs-wrapper-stdout.log
```

### 실제 로그 예시

아래는 Claude Code CLI에서 `claude`(기본 Sonnet)를 실행했을 때 래퍼 로그다. Sonnet → Codex xhigh 리맵과 Haiku → GPT-5 Mini 리맵이 동시에 동작하는 걸 볼 수 있다:

```log
📨 [messages] claude-sonnet-4-5-20250929 → gpt-5.3-codex-xhigh stream=True msgs=5
🔧 [messages] Codex effort: gpt-5.3-codex + xhigh, stream=True
INFO:     127.0.0.1:55457 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK

📨 [messages] claude-sonnet-4-5-20250929 → gpt-5.3-codex-xhigh stream=True msgs=5
🔧 [messages] Codex effort: gpt-5.3-codex + xhigh, stream=True
INFO:     127.0.0.1:55468 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK

📨 [messages] claude-haiku-4-5-20251001 → gpt-5-mini stream=True msgs=1
INFO:     127.0.0.1:55476 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK

📨 [messages] claude-opus-4-6 stream=True msgs=1
INFO:     127.0.0.1:55477 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK

📨 [messages] claude-sonnet-4-5-20250929 → gpt-5.3-codex-xhigh stream=True msgs=9
🔧 [messages] Codex effort: gpt-5.3-codex + xhigh, stream=True
INFO:     127.0.0.1:55481 - "POST /v1/messages?beta=true HTTP/1.1" 200 OK
```

**로그 읽는 법:**
- `📨` = 요청 수신. `→` 가 있으면 모델 리맵 발생
- `🔧` = Codex effort 라우팅
- `🔍` = Thinking 파라미터 삽입
- `💰` = 토큰 사용량
- `200 OK` = 정상 응답

## 엔드포인트

| 엔드포인트                       | 형식      | 용도                     |
| -------------------------------- | --------- | ------------------------ |
| `POST /v1/messages`              | Anthropic | Claude Code CLI          |
| `POST /v1/chat/completions`      | OpenAI    | VS Code Copilot BYOK     |
| `POST /v1/messages/count_tokens` | Anthropic | 토큰 카운팅 (CCS 프록시) |
| `GET /v1/models`                 | OpenAI    | 모델 목록                |
| `GET /health`                    | —         | 헬스체크                 |

## 트러블슈팅

| 증상                       | 원인                                                   | 해결                                                    |
| -------------------------- | ------------------------------------------------------ | ------------------------------------------------------- |
| `Auth conflict` 경고       | `ANTHROPIC_API_KEY`와 `ANTHROPIC_AUTH_TOKEN` 동시 설정 | `.zshrc`에서 `ANTHROPIC_API_KEY` 삭제, `claude /logout` |
| `502 unknown provider`     | Codex effort 모델을 CCS 직접 호출                      | 래퍼(:8318) 경유하도록 `ANTHROPIC_BASE_URL` 확인        |
| `Connection refused :8318` | 래퍼 미실행                                            | `launchctl start com.ccs.thinking-wrapper`              |
| `Connection refused :8317` | CCS 미실행                                             | `ccs start` 또는 `launchctl start com.ccs.cliproxy`     |
| Codex 모델 응답 없음       | Codex OAuth 만료                                       | `ccs auth add codex`로 재인증                           |

## 라이선스

MIT
