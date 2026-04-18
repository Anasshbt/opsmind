# OpsMind MVP Roadmap

## Phase 1 — Foundation (Weeks 1–3)

### Goal: Working auth + course display

**Backend**
- [ ] Database migrations (Alembic) — all models
- [ ] Auth endpoints (register, login, refresh, me)
- [ ] Course CRUD (admin seeding via script)
- [ ] Enrollment endpoint
- [ ] Health check + structured logging

**Frontend**
- [ ] Vite + React + Tailwind setup
- [ ] Login / Register pages
- [ ] Dashboard skeleton
- [ ] Course catalog with domain filters
- [ ] Course detail + module reader (Markdown)
- [ ] Auth store (Zustand) + auto-refresh

**Infra**
- [ ] docker-compose local stack (postgres, redis, backend, frontend)
- [ ] Alembic migration flow
- [ ] Dev seed script

**Milestone:** Users can register, browse courses, read markdown content.

---

## Phase 2 — Interactive Labs (Weeks 4–7)

### Goal: End-to-end lab experience

**Backend**
- [ ] DockerOrchestrator implementation
- [ ] SessionManager (start/stop/expire)
- [ ] WebSocket terminal relay
- [ ] ScoringEngine (check_task, finalize_score)
- [ ] Celery session cleanup worker

**Frontend**
- [ ] Lab catalog page
- [ ] Lab launch page
- [ ] LabWorkspace component (split pane)
- [ ] Terminal component (xterm.js + WebSocket)
- [ ] Task checklist with live feedback
- [ ] Score display modal

**Infra**
- [ ] Docker socket access for orchestrator
- [ ] Isolated lab network creation
- [ ] Lab container base images (ubuntu-lab, k8s-lab)

**Milestone:** Users can launch a lab, get a terminal, complete tasks, and get scored.

---

## Phase 3 — AI Assistant (Weeks 8–9)

### Goal: AI embedded in every lab

**Backend**
- [ ] OpenAI streaming integration
- [ ] `/ai/chat`, `/ai/explain`, `/ai/debug`, `/ai/hint` endpoints
- [ ] SSE response streaming

**Frontend**
- [ ] AIChat component with SSE streaming
- [ ] Quick action buttons (Hint, Debug, Explain)
- [ ] Typewriter animation for AI responses
- [ ] Terminal output piped to AI context

**Milestone:** Users can ask AI for help while working in the terminal.

---

## Phase 4 — Quizzes + Progress (Weeks 10–11)

**Backend**
- [ ] Quiz endpoints (get, submit, score)
- [ ] Progress tracking (enrollment progress_pct)
- [ ] User profile + score history

**Frontend**
- [ ] Quiz component (multi-choice)
- [ ] Quiz results + explanation display
- [ ] Progress bar on course cards
- [ ] Profile page with score history

---

## Phase 5 — Enterprise Module (Weeks 12–15)

**Backend**
- [ ] Enterprise CRUD
- [ ] Challenge builder
- [ ] Invite flow (token generation + email)
- [ ] ChallengeAttempt lifecycle
- [ ] Leaderboard + analytics queries

**Frontend**
- [ ] Enterprise admin dashboard
- [ ] Challenge builder UI
- [ ] Invite management
- [ ] Candidate leaderboard
- [ ] Analytics charts (Recharts)
- [ ] Candidate challenge view

---

## Phase 6 — Production Hardening (Weeks 16–18)

**Backend**
- [ ] Rate limiting (slowapi)
- [ ] Input validation hardening
- [ ] Prometheus metrics
- [ ] Query optimization (N+1 checks)
- [ ] KubernetesOrchestrator implementation
- [ ] Secrets management (Vault or K8s secrets)

**Infra**
- [ ] Kubernetes manifests (all services)
- [ ] Network policies (lab isolation)
- [ ] Ingress with TLS (cert-manager)
- [ ] HPA (Horizontal Pod Autoscaler)
- [ ] PodDisruptionBudget
- [ ] Backup strategy (postgres)

**CI/CD**
- [ ] GitHub Actions pipeline (test → build → push → deploy)
- [ ] Staging environment
- [ ] Smoke tests post-deploy

---

## Lab Image Strategy

Each domain gets a purpose-built image:

| Image | Base | Includes |
|-------|------|---------|
| `opsmind/lab-linux:latest` | ubuntu:22.04 | bash, curl, vim, systemd |
| `opsmind/lab-k8s:latest` | ubuntu + kubectl | kubectl, helm, k9s |
| `opsmind/lab-docker:latest` | ubuntu + dind | docker CLI (no daemon) |
| `opsmind/lab-network:latest` | ubuntu | nmap, tcpdump, dig, traceroute |
| `opsmind/lab-devsecops:latest` | ubuntu | trivy, bandit, semgrep |
| `opsmind/lab-terraform:latest` | ubuntu | terraform, tflint |

All images:
- Run as uid 1000
- No setuid binaries
- Minimal attack surface
- Read-only root, tmpfs for /tmp
