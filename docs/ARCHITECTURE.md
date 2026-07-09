# Architecture

One CloudFormation stack (via AWS SAM), one deploy script, no shared infrastructure. The pattern is proven by running many small independent apps on the same AWS account — each app is one stack per environment.

```
                        ┌──────────────────────────────────────────┐
Browser ──── HTTPS ───► │ CloudFront distribution                  │
                        │  • default behavior → S3Frontend (OAC)   │
                        │  • /api/*           → API Gateway        │
                        │  • 403/404          → /index.html (SPA)  │
                        └───────┬──────────────────────┬───────────┘
                                │                      │
                     ┌──────────▼─────────┐   ┌────────▼──────────────┐
                     │ S3 frontend bucket │   │ API Gateway (HTTP API)│
                     │ (private, OAC-only)│   │ stage = env name      │
                     └────────────────────┘   └────────┬──────────────┘
                                                       │ /{proxy+}
                                              ┌────────▼──────────────┐
                                              │ API Lambda            │
                                              │ FastAPI + Mangum, 60s │
                                              └──┬──────────┬─────────┘
                                    invoke(Event)│          │
                                     ┌───────────▼───┐  ┌───▼────────────────┐
                                     │ Processor     │  │ DynamoDB           │
                                     │ Lambda, 900s  │  │ users, runs (TTL)  │
                                     └───────┬───────┘  └────────────────────┘
                                             │
                                     ┌───────▼───────┐   presigned PUT/GET
                                     │ S3 data bucket│ ◄──────── Browser
                                     └───────────────┘
```

## Key decisions and why

**CloudFront as the single door.** The SPA and the API share one domain, so there are no CORS headaches in production, one TLS cert, and one URL to give the client. The frontend bucket is fully private — CloudFront reads it via Origin Access Control (sigv4), so nothing is publicly listable.

**FastAPI-in-Lambda via Mangum, one catch-all route.** The whole REST API is ordinary FastAPI code — testable with `TestClient`, runnable under uvicorn locally — and API Gateway just forwards `/{proxy+}` to it. No per-route Lambda sprawl, no framework lock-in to Lambda: the same app can move to a container later untouched. `api_gateway_base_path` strips the stage prefix API Gateway adds.

**The 60-second wall and the async worker.** CloudFront caps origin reads at 60 s, so the API Lambda must answer fast. Anything slower goes through the worker pattern: the API writes a `runs` row (`status=queued`), fires the processor Lambda with `InvocationType="Event"` (fire-and-forget), and returns `202`. The client polls `GET /api/jobs/{id}`. The processor has 15 minutes and writes `running → done|error` back to the row. Rows carry a `ttl` epoch so DynamoDB purges them automatically.

**DynamoDB pay-per-request, no VPC.** No RDS means no idle instance cost, no NAT gateway (~$32/mo each), no VPC design, and no Lambda cold-start penalty for ENI attachment. For small apps the access patterns (get by id, list by user) fit key-value + one GSI comfortably.

**Presigned S3 uploads.** API Gateway limits request bodies (10 MB) and buffering large files through Lambda wastes memory and time. Instead the API mints a 15-minute presigned PUT URL and the browser uploads straight to S3. The data bucket's CORS rule and lifecycle expiry (uploads die after a day) exist for this.

**SSM Parameter Store as the config/secret channel.** Nothing secret lives in the repo or in shell profiles. `bootstrap.sh` writes per-environment parameters (`/project/env/jwt-secret` is a SecureString); `deploy.sh` reads them at deploy time and passes them as CloudFormation parameters. Rotating a secret = update the parameter, redeploy.

**Environment namespacing.** Every resource name embeds the environment (`myapp-api-prod`, `myapp-users-test`). `--env test` gives a full, isolated copy of the system on the same account for a few cents.

**Keep-warm schedule.** A 5-minute EventBridge ping to `/api/health` keeps one API Lambda instance warm, hiding the ~1-2 s Python cold start from the first real user.

**Caching split.** Hashed Vite assets are `immutable, max-age=1y`; `index.html` is `no-cache` (it names the current hashes). `/api/*` uses the CachingDisabled managed policy. Deploys still invalidate `/*` as a belt-and-braces measure.

## Limits to know

- API responses must complete in 60 s (CloudFront) — design around the worker for anything slower.
- Lambda payload responses cap at ~6 MB — serve big files via presigned GET URLs from S3 instead.
- The keep-warm keeps **one** instance warm; a burst of parallel first requests can still cold-start extra instances.
- Custom domains require the ACM certificate to be in **us-east-1** regardless of the stack's region.
