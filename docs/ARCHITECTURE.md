# OpsMind Architecture

## System Overview

```
                          ┌──────────────────────────────────────────────────────────────┐
                          │                     OPSMIND PLATFORM                         │
                          │                                                              │
  ┌──────────┐  HTTPS     │  ┌────────────┐   REST/WS   ┌─────────────────────────────┐ │
  │ Browser  │───────────▶│  │   Nginx    │────────────▶│      FastAPI Backend        │ │
  │ (React + │  SSE/WS    │  │  (Reverse  │             │                             │ │
  │  xterm)  │◀───────────│  │   Proxy)   │             │  ┌─────────┐  ┌──────────┐  │ │
  └──────────┘            │  └────────────┘             │  │  Auth   │  │  Courses │  │ │
                          │                             │  │ /labs   │  │  /quizzes│  │ │
                          │                             │  └────┬────┘  └──────────┘  │ │
                          │                             │       │                      │ │
                          │                             │  ┌────▼──────────────────┐  │ │
                          │                             │  │   Lab Orchestrator    │  │ │
                          │                             │  │  (Docker / K8s)       │  │ │
                          │                             │  └────┬──────────────────┘  │ │
                          │                             └───────│──────────────────────┘ │
                          │                                     │                        │
                          │  ┌────────────────────────────────────────────────────────┐  │
                          │  │              Lab Sandbox Layer                         │  │
                          │  │                                                        │  │
                          │  │   ┌──────────┐  ┌──────────┐  ┌──────────┐           │  │
                          │  │   │ Lab Pod 1│  │ Lab Pod 2│  │ Lab Pod N│           │  │
                          │  │   │(uid:1000)│  │(uid:1000)│  │(uid:1000)│           │  │
                          │  │   │ No root  │  │ No root  │  │ No root  │           │  │
                          │  │   │ CPU/RAM  │  │ CPU/RAM  │  │ CPU/RAM  │           │  │
                          │  │   │ limited  │  │ limited  │  │ limited  │           │  │
                          │  │   └──────────┘  └──────────┘  └──────────┘           │  │
                          │  │                                                        │  │
                          │  │   NetworkPolicy: deny all egress                       │  │
                          │  └────────────────────────────────────────────────────────┘  │
                          │                                                              │
                          │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
                          │  │PostgreSQL│  │  Redis   │  │  OpenAI  │  │  Celery    │  │
                          │  │(data)    │  │(sessions)│  │  (AI)    │  │  (workers) │  │
                          │  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
                          └──────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### 1. Lab Isolation Strategy

Each user session gets its own container/pod with:
- **runAsUser: 1000** — no root
- **readOnlyRootFilesystem** — /tmp only via tmpfs
- **capabilities: drop ALL** — no kernel capabilities
- **NetworkPolicy: deny egress** — no internet access
- **Resource limits** — CPU and memory capped
- **TTL-based cleanup** — auto-destroyed by Celery worker

### 2. WebSocket Terminal Architecture

```
xterm.js (browser) ◄──── WebSocket ────► FastAPI WS handler
                                              │
                                              ▼
                                    docker.attach_socket()
                                              or
                                    k8s pod exec stream
                                              │
                                              ▼
                                    Container PTY (/bin/bash)
```

Authentication: JWT passed as `?token=` query parameter (browsers
can't set Authorization headers on WebSocket connections).

### 3. Scoring Engine

```
User triggers "Check Task"
         │
         ▼
Backend calls exec_command(container_id, check_script)
         │
         ▼
Script runs in container, returns exit_code 0 (pass) or non-0 (fail)
         │
         ▼
TaskResult persisted, points awarded
         │
         ▼
On submit: finalize_score() aggregates + adds time bonus
```

### 4. AI Streaming

All AI responses use SSE (Server-Sent Events):
```
POST /api/v1/ai/chat
         │
         ▼
OpenAI streaming API (stream=True)
         │
         ▼
async generator → StreamingResponse → browser
         │
         ▼
React reads ReadableStream, appends tokens to message
```

### 5. Enterprise Module Flow

```
Enterprise Admin creates Challenge
         │ defines labs, duration, time window
         ▼
Sends invite emails (tokens generated, stored in DB)
         │
         ▼
Candidate clicks link → /challenges/join/{token}
         │
         ▼
ChallengeAttempt created, lab sessions started
         │
         ▼
On submit → ScoringEngine.finalize_score()
         │
         ▼
Leaderboard updated, analytics computed
```

## Database Schema

```
users ──────────────────────────────────────┐
  id, email, username, role, ...            │
                                            │
enrollments (user_id, course_id, progress)  │
                                            │
courses ──────────────────────────────────  │
  id, title, slug, domain, difficulty       │
    └── modules                             │
          └── lessons                       │
          └── quiz                          │
                └── questions               │
                                            │
labs ──────────────────────────────────────  │
  id, title, image, cpu_limit, ...          │
    └── lab_tasks (check_script)            │
                                            │
lab_sessions ──────────────────────────────  │
  user_id → users                           │
  lab_id → labs                             │
  container_id, status, expires_at          │
    └── task_results                        │
                                            │
enterprises ───────────────────────────────  │
  id, name, owner_id → users                │
    └── enterprise_members                  │
    └── challenges                          │
          └── challenge_invites             │
          └── challenge_attempts            │
                                            │
scores ──────────────────────────────────── │
  user_id, lab_session_id, final_score      │
```

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/auth/register | Register |
| POST | /api/v1/auth/login | Login |
| POST | /api/v1/auth/refresh | Refresh tokens |
| GET | /api/v1/auth/me | Current user |
| GET | /api/v1/courses | List courses |
| POST | /api/v1/courses/{id}/enroll | Enroll |
| GET | /api/v1/labs | List labs |
| POST | /api/v1/labs/sessions | Start lab session |
| DELETE | /api/v1/labs/sessions/{id} | Stop session |
| WS | /api/v1/labs/sessions/{id}/terminal | Terminal |
| POST | /api/v1/labs/sessions/{id}/check-task | Check task |
| POST | /api/v1/labs/sessions/{id}/submit | Submit lab |
| POST | /api/v1/ai/chat | AI chat (SSE) |
| POST | /api/v1/ai/explain | Explain command (SSE) |
| POST | /api/v1/ai/debug | Debug error (SSE) |
| POST | /api/v1/ai/hint | Lab hint (SSE) |
| POST | /api/v1/enterprise | Create enterprise |
| POST | /api/v1/enterprise/{id}/challenges | Create challenge |
| POST | /api/v1/enterprise/{id}/challenges/{id}/invite | Invite candidates |
| POST | /api/v1/enterprise/join/{token} | Accept invite |
| GET | /api/v1/enterprise/{id}/challenges/{id}/leaderboard | Leaderboard |
| GET | /api/v1/enterprise/{id}/challenges/{id}/analytics | Analytics |
