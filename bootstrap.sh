#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# bootstrap.sh — one-time SSM Parameter Store setup for an environment.
#
# Creates the parameters deploy.sh reads at deploy time. Idempotent: existing
# parameters are left alone unless --force is passed.
#
# Usage:
#   ./bootstrap.sh --env <prod|staging|dev|test> [--force]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT="myapp"
AWS_PROFILE="${AWS_PROFILE_OVERRIDE:-default}"
AWS_REGION="us-east-1"
ENVIRONMENT="prod"
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)   ENVIRONMENT="$2"; shift 2 ;;
    --force) FORCE=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

SSM_PREFIX="/${PROJECT}/${ENVIRONMENT}"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; NC='\033[0m'
log()  { echo -e "${CYAN}▶ $*${NC}"; }
ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }

param_exists() {
  aws ssm get-parameter --name "$1" \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null 2>&1
}

put_param() {
  local name="$1" value="$2" type="${3:-String}"
  if param_exists "$name" && [[ "$FORCE" == "false" ]]; then
    warn "exists, skipping: $name  (use --force to overwrite)"
    return
  fi
  aws ssm put-parameter \
    --name "$name" \
    --value "$value" \
    --type "$type" \
    --overwrite \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null
  ok "set $name"
}

log "Bootstrapping SSM parameters under ${SSM_PREFIX}/ (profile: ${AWS_PROFILE}, region: ${AWS_REGION})"

# JWT secret — auto-generated, never printed
if param_exists "${SSM_PREFIX}/jwt-secret" && [[ "$FORCE" == "false" ]]; then
  warn "exists, skipping: ${SSM_PREFIX}/jwt-secret"
else
  put_param "${SSM_PREFIX}/jwt-secret" "$(openssl rand -base64 48)" "SecureString"
fi

# Bedrock model
read -r -p "Bedrock model ID [us.amazon.nova-lite-v1:0]: " BEDROCK_MODEL
put_param "${SSM_PREFIX}/bedrock-model" "${BEDROCK_MODEL:-us.amazon.nova-lite-v1:0}"

# Signup domain allowlist (empty = anyone can sign up)
read -r -p "Allowed signup email domains, comma-separated [none — open signup]: " DOMAINS
put_param "${SSM_PREFIX}/allowed-signup-domains" "${DOMAINS:-none}"
# SSM String params cannot be empty — "none" is translated to "" by deploy.sh

# Custom domain (optional)
read -r -p "ACM certificate ARN for a custom domain (us-east-1) [none]: " CERT_ARN
put_param "${SSM_PREFIX}/acm-cert-arn" "${CERT_ARN:-none}"
if [[ -n "${CERT_ARN:-}" && "${CERT_ARN:-none}" != "none" ]]; then
  read -r -p "Custom domain names, comma-separated (e.g. app.example.com): " DOMAIN_NAMES
  put_param "${SSM_PREFIX}/custom-domain-names" "${DOMAIN_NAMES:-none}"
else
  put_param "${SSM_PREFIX}/custom-domain-names" "none"
fi

echo ""
ok "Bootstrap complete. Next: ./deploy.sh --env ${ENVIRONMENT}"
