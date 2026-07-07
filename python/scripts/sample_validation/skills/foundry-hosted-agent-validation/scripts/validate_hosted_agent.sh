#!/usr/bin/env bash
#
# validate_hosted_agent.sh — automate validation of a Foundry hosted agent sample.
#
# Runs the three validation checks from the `foundry-hosted-agent-validation`
# skill and cleans up afterward:
#   1. Native local run   (uv venv + `python main.py` + curl; responses protocol)
#   2. Local via azd       (`azd ai agent init` -> `azd ai agent run` -> invoke)
#   3. Deployed            (`azd deploy` to Foundry -> `azd ai agent invoke`)
# Each check exercises a single-turn and a multi-turn (memory) exchange.
#
# ---------------------------------------------------------------------------
# DEPENDENCIES (must be installed and on PATH in the runner / pipeline)
# ---------------------------------------------------------------------------
#   bash        >= 3.2 (no bash-4-only features are used)
#   az          Azure CLI, logged in (`az login`) — used to derive the project
#               id when --project-id is omitted, and by DefaultAzureCredential.
#   azd         Azure Developer CLI, logged in (`azd auth login`), WITH the
#               agents extension installed:
#                   azd extension install azure.ai.agents
#   uv          https://docs.astral.sh/uv/ — creates the native venv & installs
#               requirements. (Note: a `python` interpreter on PATH is NOT
#               required; uv and `azd ai agent run` provision their own.)
#   curl        native HTTP invocation of the local server.
#   jq          JSON parsing of responses / `azd ai agent show` output.
#   coreutils   awk, sed, grep, tr, printf, mktemp, sleep (standard on Linux/macOS).
#
# Optional but recommended:
#   lsof OR fuser   reliable freeing of the local port during cleanup. Without
#                   them, a child server process may linger on the port.
#   Docker          NOT needed when reusing an ACR (remote build runs in ACR
#                   Tasks). Only needed if you switch to a local docker build.
#
# ---------------------------------------------------------------------------
# REQUIRED INPUTS (flags or environment variables)
# ---------------------------------------------------------------------------
#   --project-endpoint  | FOUNDRY_PROJECT_ENDPOINT          (native + all phases)
#   --model             | AZURE_AI_MODEL_DEPLOYMENT_NAME    (a REAL deployed model)
#   --project-id        | FOUNDRY_PROJECT_ID                (azd-local + deploy)
#   --acr-endpoint      | AZURE_CONTAINER_REGISTRY_ENDPOINT (deploy only)
#
# If --project-id is omitted it is derived from the endpoint via `az`.
#
# ---------------------------------------------------------------------------
# USAGE
# ---------------------------------------------------------------------------
#   validate_hosted_agent.sh [options]
#
#   --sample-dir DIR        Sample folder (default: the responses/01_basic sample
#                           resolved relative to this script's repo).
#   --project-endpoint URL  Foundry project endpoint.
#   --project-id ID         Foundry project ARM resource id.
#   --model NAME            Real model deployment name in the project.
#   --acr-endpoint HOST     Existing ACR login server (e.g. myacr.azurecr.io).
#   --agent-name NAME       Override agent/service name (default: read agent.yaml).
#   --port N                Local port (default: 8088).
#   --skip-native           Skip phase 1 (native local run).
#   --skip-azd-local        Skip phase 2 (azd ai agent run).
#   --skip-deploy           Skip phase 3 (deploy to Foundry).
#   --keep-agent            Do NOT delete the deployed agent during cleanup.
#   --no-cleanup            Keep temp azd project, sample .env/.venv, and agent.
#   -h | --help             Show this help.
#
# EXIT CODES: 0 = all enabled checks passed; non-zero = a check or setup failed.
#
set -euo pipefail

# --------------------------- pretty logging --------------------------------
_c() { [ -t 1 ] && printf '%s' "$1" || printf ''; }
log()  { printf '%s[validate]%s %s\n' "$(_c $'\033[1;34m')" "$(_c $'\033[0m')" "$*"; }
ok()   { printf '%s[ pass ]%s %s\n'  "$(_c $'\033[1;32m')" "$(_c $'\033[0m')" "$*"; }
warn() { printf '%s[ warn ]%s %s\n'  "$(_c $'\033[1;33m')" "$(_c $'\033[0m')" "$*" >&2; }
die()  { printf '%s[ FAIL ]%s %s\n'  "$(_c $'\033[1;31m')" "$(_c $'\033[0m')" "$*" >&2; exit 1; }

# --------------------------- defaults / args -------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# scripts -> foundry-hosted-agent-validation -> skills -> sample_validation -> scripts -> python
PYTHON_ROOT="$(cd "$SCRIPT_DIR/../../../../.." && pwd)"
DEFAULT_SAMPLE="$PYTHON_ROOT/samples/04-hosting/foundry-hosted-agents/responses/01_basic"

SAMPLE_DIR="${DEFAULT_SAMPLE}"
PROJECT_ENDPOINT="${FOUNDRY_PROJECT_ENDPOINT:-}"
PROJECT_ID="${FOUNDRY_PROJECT_ID:-}"
MODEL="${AZURE_AI_MODEL_DEPLOYMENT_NAME:-}"
ACR_ENDPOINT="${AZURE_CONTAINER_REGISTRY_ENDPOINT:-}"
AGENT_NAME=""
PORT=8088
DO_NATIVE=1; DO_AZD_LOCAL=1; DO_DEPLOY=1
KEEP_AGENT=0; DO_CLEANUP=1

usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//; s/^#//' | sed '$d'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --sample-dir)       SAMPLE_DIR="$2"; shift 2;;
    --project-endpoint) PROJECT_ENDPOINT="$2"; shift 2;;
    --project-id)       PROJECT_ID="$2"; shift 2;;
    --model)            MODEL="$2"; shift 2;;
    --acr-endpoint)     ACR_ENDPOINT="$2"; shift 2;;
    --agent-name)       AGENT_NAME="$2"; shift 2;;
    --port)             PORT="$2"; shift 2;;
    --skip-native)      DO_NATIVE=0; shift;;
    --skip-azd-local)   DO_AZD_LOCAL=0; shift;;
    --skip-deploy)      DO_DEPLOY=0; shift;;
    --keep-agent)       KEEP_AGENT=1; shift;;
    --no-cleanup)       DO_CLEANUP=0; KEEP_AGENT=1; shift;;
    -h|--help)          usage; exit 0;;
    *) die "unknown argument: $1 (use --help)";;
  esac
done

# --------------------------- state / cleanup -------------------------------
WORK_DIR=""; PROJECT_ROOT=""; NATIVE_PID=""; AZD_RUN_PID=""
DEPLOYED=0; CREATED_ENV=0; CREATED_VENV=0
PASS_COUNT=0; FAIL_COUNT=0; SUMMARY=""

record() { # $1=pass|fail  $2=text
  if [ "$1" = pass ]; then PASS_COUNT=$((PASS_COUNT+1)); SUMMARY="${SUMMARY}  [pass] $2"$'\n';
  else FAIL_COUNT=$((FAIL_COUNT+1)); SUMMARY="${SUMMARY}  [FAIL] $2"$'\n'; fi
}

free_port() { # $1=port
  local port="$1" pids
  if command -v lsof >/dev/null 2>&1; then
    pids="$(lsof -ti "tcp:${port}" 2>/dev/null || true)"
    [ -n "$pids" ] && kill -9 $pids 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

stop_bg() { # $1=pid  $2=port
  local pid="${1:-}" port="${2:-}"
  if [ -n "$pid" ]; then kill "$pid" 2>/dev/null || true; sleep 1; kill -9 "$pid" 2>/dev/null || true; fi
  [ -n "$port" ] && free_port "$port"
}

cleanup() {
  local ec=$?
  log "cleanup..."
  stop_bg "$NATIVE_PID" "$PORT"
  stop_bg "$AZD_RUN_PID" "$PORT"
  if [ "$DO_CLEANUP" = 1 ]; then
    if [ "$DEPLOYED" = 1 ] && [ "$KEEP_AGENT" = 0 ] && [ -n "$PROJECT_ROOT" ] && [ -d "$PROJECT_ROOT" ]; then
      log "deleting deployed agent '$AGENT_NAME'"
      ( cd "$PROJECT_ROOT" && azd ai agent delete "$AGENT_NAME" --force --no-prompt >/dev/null 2>&1 ) || \
        warn "could not delete deployed agent (delete it manually)"
    fi
    [ "$CREATED_ENV" = 1 ] && rm -f "$SAMPLE_DIR/.env" 2>/dev/null || true
    [ "$CREATED_VENV" = 1 ] && rm -rf "$SAMPLE_DIR/.venv" 2>/dev/null || true
    [ -n "$WORK_DIR" ] && rm -rf "$WORK_DIR" 2>/dev/null || true
  else
    warn "cleanup skipped (--no-cleanup). Temp project: ${WORK_DIR:-n/a}"
  fi
  if [ "$ec" -ne 0 ]; then printf '\n'; die "aborted (exit $ec)"; fi
}
trap cleanup EXIT INT TERM

# --------------------------- preflight -------------------------------------
require_cmd() { command -v "$1" >/dev/null 2>&1 || die "missing dependency '$1' — $2"; }

log "preflight: checking dependencies"
require_cmd az   "install Azure CLI: https://aka.ms/azcli"
require_cmd azd  "install Azure Developer CLI: https://aka.ms/azd"
require_cmd uv   "install uv: https://docs.astral.sh/uv/"
require_cmd curl "install curl"
require_cmd jq   "install jq: https://jqlang.github.io/jq/"
require_cmd awk  "install coreutils (awk)"
require_cmd mktemp "install coreutils (mktemp)"

az account show >/dev/null 2>&1 || die "not logged in to Azure CLI — run: az login"
azd auth login --check-status >/dev/null 2>&1 || die "not logged in to azd — run: azd auth login"
azd extension list 2>/dev/null | grep -qi 'azure.ai.agents' || \
  die "azd agents extension missing — run: azd extension install azure.ai.agents"
command -v lsof >/dev/null 2>&1 || command -v fuser >/dev/null 2>&1 || \
  warn "neither lsof nor fuser found; port ${PORT} may not be freed cleanly on exit"

[ -d "$SAMPLE_DIR" ] || die "sample dir not found: $SAMPLE_DIR"
[ -f "$SAMPLE_DIR/main.py" ] || die "no main.py in sample dir: $SAMPLE_DIR"
[ -f "$SAMPLE_DIR/agent.yaml" ] || die "no agent.yaml in sample dir: $SAMPLE_DIR"
[ -n "$MODEL" ] || die "model deployment name required (--model or AZURE_AI_MODEL_DEPLOYMENT_NAME)"

# derive agent name + protocol from agent.yaml
if [ -z "$AGENT_NAME" ]; then
  AGENT_NAME="$(grep -E '^name:' "$SAMPLE_DIR/agent.yaml" | head -1 | sed -E 's/^name:[[:space:]]*//' | tr -d '"'\''\r')"
fi
[ -n "$AGENT_NAME" ] || die "could not determine agent name (pass --agent-name)"
PROTOCOL="$(grep -oE 'protocol:[[:space:]]*[a-zA-Z]+' "$SAMPLE_DIR/agent.yaml" | head -1 | sed -E 's/protocol:[[:space:]]*//')"
[ -n "$PROTOCOL" ] || PROTOCOL=responses

WORK_DIR="$(mktemp -d 2>/dev/null || mktemp -d -t afval)"
log "sample=$SAMPLE_DIR"
log "agent=$AGENT_NAME  protocol=$PROTOCOL  model=$MODEL  port=$PORT"
log "workdir=$WORK_DIR"

# --------------------------- helpers ---------------------------------------
wait_http() { # $1=url  $2=timeout_s
  local url="$1" timeout="${2:-90}" i=0 code
  while :; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 "$url" 2>/dev/null || echo 000)"
    [ "$code" != "000" ] && return 0
    i=$((i+1)); [ "$i" -ge "$timeout" ] && return 1; sleep 1
  done
}

# assert an `azd ai agent invoke --output raw` SSE stream succeeded.
# $1 = raw output ; $2 = optional expected substring (case-insensitive)
check_sse() {
  local raw="$1" expect="${2:-}"
  printf '%s' "$raw" | grep -qi 'DeploymentNotFound' && { warn "DeploymentNotFound"; return 2; }
  printf '%s' "$raw" | grep -q 'response.failed'      && { warn "response.failed";  return 2; }
  printf '%s' "$raw" | grep -q 'response.completed'   || { warn "no response.completed"; return 3; }
  if [ -n "$expect" ]; then printf '%s' "$raw" | grep -qi "$expect" || { warn "missing '$expect'"; return 4; }; fi
  return 0
}

resolve_project_id() {
  [ -n "$PROJECT_ID" ] && return 0
  [ -n "$PROJECT_ENDPOINT" ] || die "need --project-id or --project-endpoint to resolve the project"
  # endpoint: https://<account>.services.ai.azure.com/api/projects/<project>
  local acct proj
  acct="$(printf '%s' "$PROJECT_ENDPOINT" | sed -E 's#https?://([^.]+)\..*#\1#')"
  proj="$(printf '%s' "$PROJECT_ENDPOINT" | sed -E 's#.*/projects/([^/?]+).*#\1#')"
  [ -n "$acct" ] && [ -n "$proj" ] || die "could not parse account/project from endpoint"
  local acct_id
  acct_id="$(az cognitiveservices account list --query "[?name=='${acct}'].id | [0]" -o tsv 2>/dev/null || true)"
  [ -n "$acct_id" ] || die "could not find Foundry account '$acct' via az (check subscription/login)"
  PROJECT_ID="${acct_id}/projects/${proj}"
  log "resolved project-id=$PROJECT_ID"
}

# service-name -> AGENT_{KEY}_NAME env var used by `azd ai agent delete/show`
name_key() { # $1=service name
  local k; k="$(printf '%s' "$1" | tr 'a-z' 'A-Z' | tr '-' '_' | tr ' ' '_')"
  printf 'AGENT_%s_NAME' "$k"
}

INITED=0
ensure_azd_project() {
  [ "$INITED" = 1 ] && return 0
  resolve_project_id
  # Remove a local .venv from the sample dir so `init` doesn't copy it into src/.
  [ -d "$SAMPLE_DIR/.venv" ] && [ "$CREATED_VENV" = 1 ] && { rm -rf "$SAMPLE_DIR/.venv"; CREATED_VENV=0; }

  log "azd ai agent init (this can take a few minutes)"
  ( cd "$WORK_DIR" && azd ai agent init \
      -m "$SAMPLE_DIR/agent.manifest.yaml" \
      --project-id "$PROJECT_ID" \
      --model-deployment "$MODEL" \
      --agent-name "$AGENT_NAME" \
      --no-prompt --force ) >"$WORK_DIR/init.log" 2>&1 \
    || { tail -n 40 "$WORK_DIR/init.log" >&2; die "azd ai agent init failed"; }

  PROJECT_ROOT="$WORK_DIR/$AGENT_NAME"
  [ -f "$PROJECT_ROOT/azure.yaml" ] || die "azd project not found at $PROJECT_ROOT after init"

  # GOTCHA fix: init hardcodes the manifest model into the generated agent.yaml.
  # Restore the template so `azd deploy` substitutes the azd env value.
  local ay="$PROJECT_ROOT/src/$AGENT_NAME/agent.yaml"
  if [ -f "$ay" ]; then
    awk '
      seen && /value:/ { sub(/value:.*/, "value: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}"); seen=0 }
      /- name: AZURE_AI_MODEL_DEPLOYMENT_NAME/ { seen=1 }
      { print }
    ' "$ay" > "$ay.tmp" && mv "$ay.tmp" "$ay"
  fi

  ( cd "$PROJECT_ROOT" && azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$MODEL" >/dev/null )
  INITED=1
}

# ========================= PHASE 1: native local ===========================
if [ "$DO_NATIVE" = 1 ]; then
  [ "$PROTOCOL" = responses ] || { warn "phase 1 (native curl) supports 'responses'; sample is '$PROTOCOL' — skipping"; DO_NATIVE=0; }
fi
if [ "$DO_NATIVE" = 1 ]; then
  log "=== Phase 1: native local run ==="
  [ -n "$PROJECT_ENDPOINT" ] || die "native run needs --project-endpoint (FOUNDRY_PROJECT_ENDPOINT)"

  printf 'FOUNDRY_PROJECT_ENDPOINT="%s"\nAZURE_AI_MODEL_DEPLOYMENT_NAME="%s"\n' \
    "$PROJECT_ENDPOINT" "$MODEL" > "$SAMPLE_DIR/.env"; CREATED_ENV=1

  log "creating venv + installing requirements (uv)"
  uv venv "$SAMPLE_DIR/.venv" --python 3.12 >"$WORK_DIR/venv.log" 2>&1 || { cat "$WORK_DIR/venv.log" >&2; die "uv venv failed"; }
  CREATED_VENV=1
  if   [ -x "$SAMPLE_DIR/.venv/bin/python" ];        then VENV_PY="$SAMPLE_DIR/.venv/bin/python"
  elif [ -x "$SAMPLE_DIR/.venv/Scripts/python.exe" ]; then VENV_PY="$SAMPLE_DIR/.venv/Scripts/python.exe"
  else die "venv python not found under $SAMPLE_DIR/.venv"; fi
  uv pip install --python "$VENV_PY" -r "$SAMPLE_DIR/requirements.txt" >"$WORK_DIR/pip.log" 2>&1 \
    || { tail -n 30 "$WORK_DIR/pip.log" >&2; die "uv pip install failed"; }

  log "starting server: python main.py (:$PORT)"
  ( cd "$SAMPLE_DIR" && exec "$VENV_PY" main.py ) >"$WORK_DIR/native-server.log" 2>&1 &
  NATIVE_PID=$!
  wait_http "http://localhost:$PORT/responses" 90 || { tail -n 40 "$WORK_DIR/native-server.log" >&2; die "native server did not start on :$PORT"; }

  log "invoke: turn 1 (set name)"
  b1="$(curl -sS -X POST "http://localhost:$PORT/responses" -H 'Content-Type: application/json' \
        -d '{"input":"My name is Tao. Please remember it."}')"
  [ "$(printf '%s' "$b1" | jq -r '.status // empty')" = completed ] || die "native turn1 not completed: $b1"
  rid="$(printf '%s' "$b1" | jq -r '.response_id // empty')"
  [ -n "$rid" ] || die "native turn1 missing response_id"

  log "invoke: turn 2 (recall via previous_response_id)"
  b2="$(curl -sS -X POST "http://localhost:$PORT/responses" -H 'Content-Type: application/json' \
        -d "$(jq -nc --arg id "$rid" '{input:"What is my name?", previous_response_id:$id}')")"
  t2="$(printf '%s' "$b2" | jq -r '.output[0].content[0].text // empty')"
  printf '%s' "$t2" | grep -qi 'Tao' || die "native multi-turn recall failed (got: '$t2')"
  ok "native local: single + multi-turn (recall: '$t2')"; record pass "native local (python main.py)"

  stop_bg "$NATIVE_PID" "$PORT"; NATIVE_PID=""
else
  log "skipping Phase 1 (native local)"
fi

# ========================= PHASE 2: azd local ==============================
if [ "$DO_AZD_LOCAL" = 1 ]; then
  log "=== Phase 2: local via 'azd ai agent run' ==="
  ensure_azd_project

  log "starting: azd ai agent run --no-inspector (:$PORT)"
  ( cd "$PROJECT_ROOT" && exec azd ai agent run --no-inspector --port "$PORT" ) >"$WORK_DIR/azd-run.log" 2>&1 &
  AZD_RUN_PID=$!
  wait_http "http://localhost:$PORT/responses" 240 || { tail -n 60 "$WORK_DIR/azd-run.log" >&2; die "azd ai agent run did not start on :$PORT"; }

  log "invoke --local: turn 1 (set name)"
  r1="$( ( cd "$PROJECT_ROOT" && azd ai agent invoke --local --protocol "$PROTOCOL" --output raw --new-session \
           "My name is Tao. Please remember it." ) 2>&1 || true )"
  check_sse "$r1" || die "azd local turn1 failed"
  log "invoke --local: turn 2 (recall, same session)"
  r2="$( ( cd "$PROJECT_ROOT" && azd ai agent invoke --local --protocol "$PROTOCOL" --output raw \
           "What is my name?" ) 2>&1 || true )"
  check_sse "$r2" "Tao" || die "azd local multi-turn recall failed"
  ok "azd local: single + multi-turn"; record pass "azd local (azd ai agent run)"

  stop_bg "$AZD_RUN_PID" "$PORT"; AZD_RUN_PID=""
else
  log "skipping Phase 2 (azd local)"
fi

# ========================= PHASE 3: deploy =================================
if [ "$DO_DEPLOY" = 1 ]; then
  log "=== Phase 3: deploy to Foundry ==="
  [ -n "$ACR_ENDPOINT" ] || die "deploy needs --acr-endpoint (AZURE_CONTAINER_REGISTRY_ENDPOINT) to reuse an ACR"
  ensure_azd_project

  ( cd "$PROJECT_ROOT" && azd env set AZURE_CONTAINER_REGISTRY_ENDPOINT "$ACR_ENDPOINT" >/dev/null )

  # Ensure a clean deploy: best-effort delete a pre-existing agent of this name.
  log "removing any pre-existing agent named '$AGENT_NAME'"
  NK="$(name_key "$AGENT_NAME")"
  ( cd "$PROJECT_ROOT" && azd env set "$NK" "$AGENT_NAME" >/dev/null )
  ( cd "$PROJECT_ROOT" && azd ai agent delete "$AGENT_NAME" --force --no-prompt >/dev/null 2>&1 ) \
    && log "deleted pre-existing agent" || log "no pre-existing agent to delete"

  log "azd deploy (remote build via ACR; can take a few minutes)"
  ( cd "$PROJECT_ROOT" && azd deploy ) >"$WORK_DIR/deploy.log" 2>&1 \
    || { tail -n 60 "$WORK_DIR/deploy.log" >&2; die "azd deploy failed"; }
  DEPLOYED=1
  ok "azd deploy succeeded"

  log "verify deployed model env var"
  shown="$( cd "$PROJECT_ROOT" && azd ai agent show "$AGENT_NAME" --output json 2>/dev/null || true )"
  dep_model="$(printf '%s' "$shown" | jq -r '.definition.environment_variables.AZURE_AI_MODEL_DEPLOYMENT_NAME // empty')"
  [ "$dep_model" = "$MODEL" ] || die "deployed model env var is '$dep_model', expected '$MODEL'"
  status="$(printf '%s' "$shown" | jq -r '.status // empty')"
  [ "$status" = active ] || warn "deployed agent status is '$status' (expected active)"
  log "deployed model=$dep_model status=$status"

  log "invoke deployed: turn 1 (set name)"
  d1="$( ( cd "$PROJECT_ROOT" && azd ai agent invoke "$AGENT_NAME" --protocol "$PROTOCOL" --output raw --new-session \
           "My name is Tao. Please remember it." ) 2>&1 || true )"
  check_sse "$d1" || die "deployed turn1 failed"
  log "invoke deployed: turn 2 (recall, same session)"
  d2="$( ( cd "$PROJECT_ROOT" && azd ai agent invoke "$AGENT_NAME" --protocol "$PROTOCOL" --output raw \
           "What is my name?" ) 2>&1 || true )"
  check_sse "$d2" "Tao" || die "deployed multi-turn recall failed"
  ok "deployed: single + multi-turn"; record pass "deployed (azd deploy + invoke)"
else
  log "skipping Phase 3 (deploy)"
fi

# ============================= summary =====================================
printf '\n===================== validation summary =====================\n'
printf '%s' "$SUMMARY"
printf '==============================================================\n'
printf 'passed: %d   failed: %d\n' "$PASS_COUNT" "$FAIL_COUNT"
[ "$FAIL_COUNT" -eq 0 ] || exit 1
log "all enabled checks passed"
