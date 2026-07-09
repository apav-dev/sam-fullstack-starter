#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — build and deploy the full stack.
#
#   1. Stage api/ + requirements.txt + Makefile into lambda/ (SAM build dir)
#   2. Build the frontend (Vite)
#   3. sam build && sam deploy (params come from SSM — run ./bootstrap.sh once)
#   4. Sync frontend/dist/ to the frontend S3 bucket
#   5. Invalidate the CloudFront cache
#   6. Run the Playwright smoke test against the live URL
#
# Prerequisites: AWS SAM CLI, AWS CLI (configured profile), uv, Node.js + pnpm.
#
# Usage:
#   ./deploy.sh [--env <prod|staging|dev|test>] [--skip-frontend] [--skip-build] [--skip-tests]
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults (init.sh rewrites PROJECT/profile/region) ────────────────────────
PROJECT="myapp"
AWS_PROFILE="${AWS_PROFILE_OVERRIDE:-default}"
AWS_REGION="us-east-1"
ENVIRONMENT="prod"
SKIP_FRONTEND=false
SKIP_BUILD=false
SKIP_TESTS=false
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)           ENVIRONMENT="$2"; shift 2 ;;
    --skip-frontend) SKIP_FRONTEND=true; shift ;;
    --skip-build)    SKIP_BUILD=true;    shift ;;
    --skip-tests)    SKIP_TESTS=true;    shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

STACK_NAME="${PROJECT}-${ENVIRONMENT}"
SSM_PREFIX="/${PROJECT}/${ENVIRONMENT}"

# ── Colours ───────────────────────────────────────────────────────────────────
BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${CYAN}▶ $*${NC}"; }
ok()   { echo -e "${GREEN}✔ $*${NC}"; }
warn() { echo -e "${YELLOW}⚠ $*${NC}"; }
die()  { echo -e "${RED}✖ $*${NC}"; exit 1; }

cd "$SCRIPT_DIR"

# ── Prod confirmation ─────────────────────────────────────────────────────────
if [[ "$ENVIRONMENT" == "prod" ]]; then
  echo "You are about to deploy to PRODUCTION (stack: ${STACK_NAME})."
  read -r -p "Enter 'yes' to continue: " confirm
  [[ "$confirm" == "yes" ]] || { echo "Deployment cancelled."; exit 1; }
fi

# ── Version stamp ─────────────────────────────────────────────────────────────
GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unversioned)"
if ! git diff --quiet HEAD 2>/dev/null; then
  GIT_SHA="${GIT_SHA}-dirty"
fi
APP_VERSION="$(git describe --tags --abbrev=0 2>/dev/null || echo dev)"

echo -e "${BOLD}"
echo "  ${PROJECT} — deploy"
echo "  env: ${ENVIRONMENT}  •  profile: ${AWS_PROFILE}  •  region: ${AWS_REGION}"
echo "  version: ${APP_VERSION} (${GIT_SHA})"
echo -e "${NC}"

# ── Verify tools ──────────────────────────────────────────────────────────────
log "Checking required tools…"
command -v sam  >/dev/null 2>&1 || die "AWS SAM CLI not found."
command -v aws  >/dev/null 2>&1 || die "AWS CLI not found."
command -v uv   >/dev/null 2>&1 || die "uv not found (https://docs.astral.sh/uv/)."
command -v node >/dev/null 2>&1 || die "Node.js not found."
command -v pnpm >/dev/null 2>&1 || die "pnpm not found (npm install -g pnpm)."
ok "All tools present"

log "Verifying AWS credentials (profile: ${AWS_PROFILE})…"
aws sts get-caller-identity --profile "$AWS_PROFILE" --region "$AWS_REGION" --output json \
  | grep -q '"UserId"' || die "AWS credentials invalid for profile '${AWS_PROFILE}'"
ok "AWS credentials valid"

# ── Fetch deploy-time config from SSM ────────────────────────────────────────
log "Fetching config from SSM (${SSM_PREFIX}/*)…"

ssm_get() {
  aws ssm get-parameter \
    --name "$1" --with-decryption \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" \
    --query "Parameter.Value" --output text 2>/dev/null \
    || die "SSM parameter not found: $1 — run ./bootstrap.sh --env ${ENVIRONMENT} first"
}

# "none" is the bootstrap.sh sentinel for empty (SSM forbids empty String values)
unnone() { [[ "$1" == "none" ]] && echo "" || echo "$1"; }

JWT_SECRET=$(ssm_get "${SSM_PREFIX}/jwt-secret")
BEDROCK_MODEL=$(ssm_get "${SSM_PREFIX}/bedrock-model")
ALLOWED_SIGNUP_EMAIL_DOMAINS=$(unnone "$(ssm_get "${SSM_PREFIX}/allowed-signup-domains")")
ACM_CERTIFICATE_ARN=$(unnone "$(ssm_get "${SSM_PREFIX}/acm-cert-arn")")
CUSTOM_DOMAIN_NAMES=$(unnone "$(ssm_get "${SSM_PREFIX}/custom-domain-names")")
ok "SSM config loaded"

# ── Step 1: Stage Lambda sources ──────────────────────────────────────────────
if [[ "$SKIP_BUILD" == "false" ]]; then
  log "Staging Lambda source files → lambda/ …"
  rm -rf lambda/
  mkdir -p lambda/
  cp -r api/ lambda/api/
  cp requirements.txt Makefile lambda/
  ok "Lambda sources staged"

  # ── Step 2: Build frontend ─────────────────────────────────────────────────
  if [[ "$SKIP_FRONTEND" == "false" ]]; then
    log "Building frontend (Vite)…"
    (
      cd frontend
      pnpm install --frozen-lockfile
      pnpm build
    )
    ok "Frontend built → frontend/dist/"
  fi

  # ── Step 3: SAM build ─────────────────────────────────────────────────────
  log "Running SAM build…"
  sam build --template-file template.yaml --build-dir .aws-sam/build --parallel
  ok "SAM build complete"
fi

# ── Step 4: SAM deploy ────────────────────────────────────────────────────────
log "Deploying SAM stack '${STACK_NAME}'…"

# A stack stuck in ROLLBACK_COMPLETE (failed first create) must be deleted
# before CloudFormation will accept a new create.
STACK_STATUS=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" --region "$AWS_REGION" --profile "$AWS_PROFILE" \
  --query "Stacks[0].StackStatus" --output text 2>/dev/null || echo "DOES_NOT_EXIST")

if [[ "$STACK_STATUS" == "ROLLBACK_COMPLETE" ]]; then
  warn "Stack is in ROLLBACK_COMPLETE — deleting so we can create fresh…"
  aws cloudformation delete-stack \
    --stack-name "$STACK_NAME" --region "$AWS_REGION" --profile "$AWS_PROFILE"
  aws cloudformation wait stack-delete-complete \
    --stack-name "$STACK_NAME" --region "$AWS_REGION" --profile "$AWS_PROFILE"
  ok "Old stack deleted"
fi

sam deploy \
  --template-file .aws-sam/build/template.yaml \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --profile "$AWS_PROFILE" \
  --capabilities CAPABILITY_IAM \
  --s3-prefix "$PROJECT" \
  --resolve-s3 \
  --no-fail-on-empty-changeset \
  --parameter-overrides \
      "Environment=${ENVIRONMENT}" \
      "BedrockModel=${BEDROCK_MODEL}" \
      "JwtSecret=${JWT_SECRET}" \
      "AllowedSignupEmailDomains=${ALLOWED_SIGNUP_EMAIL_DOMAINS}" \
      "CustomDomainNames=${CUSTOM_DOMAIN_NAMES}" \
      "AcmCertificateArn=${ACM_CERTIFICATE_ARN}" \
      "AppVersion=${APP_VERSION}" \
      "GitSha=${GIT_SHA}"

ok "SAM stack deployed"

# ── Step 5: Fetch stack outputs ───────────────────────────────────────────────
get_output() {
  aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" --region "$AWS_REGION" --profile "$AWS_PROFILE" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

CLOUDFRONT_URL=$(get_output "CloudFrontUrl")
CLOUDFRONT_ID=$(get_output "CloudFrontDistributionId")
FRONTEND_BUCKET=$(get_output "FrontendBucketName")
API_URL=$(get_output "ApiUrl")

echo ""
echo -e "  ${BOLD}Stack outputs:${NC}"
echo "    CloudFront URL  : ${CLOUDFRONT_URL}"
echo "    API URL         : ${API_URL}"
echo "    Frontend bucket : ${FRONTEND_BUCKET}"
echo ""

# ── Step 6: Sync frontend to S3 ───────────────────────────────────────────────
if [[ "$SKIP_FRONTEND" == "false" ]]; then
  log "Syncing frontend/dist/ → s3://${FRONTEND_BUCKET}/ …"
  # Hashed assets: cache forever
  aws s3 sync frontend/dist/ "s3://${FRONTEND_BUCKET}/" \
    --region "$AWS_REGION" --profile "$AWS_PROFILE" \
    --delete \
    --cache-control "public,max-age=31536000,immutable" \
    --exclude "index.html"
  # index.html: never cached (it names the current asset hashes)
  aws s3 cp frontend/dist/index.html "s3://${FRONTEND_BUCKET}/index.html" \
    --region "$AWS_REGION" --profile "$AWS_PROFILE" \
    --cache-control "no-cache,no-store,must-revalidate" \
    --content-type "text/html"
  ok "Frontend synced"

  log "Creating CloudFront invalidation…"
  aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_ID" --paths "/*" \
    --profile "$AWS_PROFILE" \
    --query "Invalidation.Id" --output text >/dev/null
  ok "Cache invalidated"
fi

# ── Step 7: Post-deploy smoke test ───────────────────────────────────────────
if [[ "$SKIP_TESTS" == "false" ]]; then
  log "Running Playwright smoke test against ${CLOUDFRONT_URL} …"
  if [[ ! -d node_modules ]]; then
    warn "Repo-root node_modules missing — run 'pnpm install' at repo root to enable smoke tests"
  else
    E2E_BASE_URL="$CLOUDFRONT_URL" pnpm exec playwright test \
      || die "Smoke test FAILED — the deploy is live but unhealthy"
    ok "Smoke test passed"
  fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  ✔ Deployment complete!${NC}"
echo ""
echo -e "  ${BOLD}App URL:${NC} ${CLOUDFRONT_URL}"
echo ""
echo "  Tail Lambda logs:"
echo "    sam logs --stack-name ${STACK_NAME} --profile ${AWS_PROFILE} --region ${AWS_REGION} --tail"
echo ""
