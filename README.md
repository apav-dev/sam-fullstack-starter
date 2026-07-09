# sam-fullstack-starter

One-shot AWS deployment for a full-stack serverless app: **Vite/React SPA on CloudFront + FastAPI in Lambda + DynamoDB + S3**, all in a single SAM stack. Working account creation and login out of the box.

Designed for the "client has no cloud infrastructure" scenario: fresh AWS account → running app in three commands. Near-zero cost when idle (no VPC, no RDS, no NAT — everything pay-per-request).

```
Browser ──► CloudFront (one distribution, two origins)
              ├─ default:  S3 frontend bucket   (private; OAC)
              └─ /api/*:   API Gateway ──► API Lambda (FastAPI + Mangum, 60 s)
                                              └─ invokes Processor Lambda (async jobs, 15 min)
DynamoDB: users, runs (TTL)        S3 data bucket: presigned uploads, job outputs
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full rationale.

## Quickstart

Prerequisites: [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html), AWS CLI (configured profile), [uv](https://docs.astral.sh/uv/), Node.js 20+, pnpm.

```bash
# 1. Instantiate the template (rewrites the "myapp" placeholder everywhere, single-use)
./init.sh acme --profile acme-prod --region us-east-1

# 2. Create the SSM parameters for an environment (JWT secret auto-generated)
./bootstrap.sh --env prod

# 3. Build + deploy everything (SAM stack, frontend to S3, CloudFront invalidation, smoke test)
./deploy.sh --env prod
```

The deploy prints the CloudFront URL. First visitor to sign up becomes **admin**.

Onboarding a brand-new AWS account? Follow [docs/CLIENT-ONBOARDING.md](docs/CLIENT-ONBOARDING.md).

## What's included

| Piece | Where | Notes |
|---|---|---|
| Email/password auth (JWT) | `api/auth_utils.py`, `api/routes/auth.py` | PBKDF2 + HS256; first user auto-admin; optional signup domain allowlist |
| Okta SSO (optional) | same | Set `OktaIssuer`/`OktaClientId` params to enable; off by default |
| Presigned S3 upload | `api/routes/uploads.py` | Browser PUTs directly to S3 — no API Gateway body-size limit |
| Async worker pattern | `api/routes/jobs.py`, `api/processor.py` | API fires processor Lambda (Event), client polls; demo job word-counts a file |
| Bedrock LLM example | `api/routes/ai.py` | One `converse` call; model ID from SSM |
| Multi-env | `--env prod\|staging\|dev\|test` | Every resource namespaced; independent stacks |
| Custom domain | SSM `acm-cert-arn` + `custom-domain-names` | Conditional CloudFront alias + cert |
| Keep-warm | `template.yaml` KeepWarm event | 5-min health ping avoids cold starts |
| Post-deploy smoke test | `tests/e2e/smoke.spec.ts` | Playwright signs up / logs in against the live URL |

## Local development

No AWS needed — the API falls back to in-memory storage when table env vars are unset.

```bash
./scripts/local-dev.sh            # FastAPI on :8000
cd frontend && pnpm dev           # Vite on :5173, proxies /api → :8000
```

Tests:

```bash
uv run pytest                     # backend unit tests
pnpm exec playwright test         # E2E against local dev (or E2E_BASE_URL=<url>)
```

## Deploy variants

```bash
./deploy.sh --env test                    # non-prod: no confirmation prompt
./deploy.sh --env prod --skip-frontend    # backend-only change
./deploy.sh --env prod --skip-build       # redeploy existing build artifacts
./deploy.sh --env prod --skip-tests       # skip the Playwright smoke test
```

## Where to build your app

- **API routes**: add a file under `api/routes/`, include it in `api/main.py`
- **Slow work (>60 s)**: put it in `api/processor.py` (or clone it into a second worker function in `template.yaml`)
- **Frontend**: `frontend/src/pages/` — `HomePage.tsx` shows the upload/job/AI call patterns; replace it
- **New tables/buckets**: add to `template.yaml`, wire the name through `Globals → Environment` and IAM `Policies`

## Cost notes

Idle cost is a few cents/month (CloudFront + S3 storage + the keep-warm invocations, which sit inside the Lambda free tier). Everything else is pay-per-request. Deleting a stack removes everything except non-empty S3 buckets (empty them first).
