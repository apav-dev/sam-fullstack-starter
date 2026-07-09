# Client onboarding — fresh AWS account to running app

Checklist for standing this stack up for a client who has no cloud infrastructure.

## 1. AWS account + access

1. Client creates an AWS account (or you create one under their organization). Enable MFA on the root user, then stop using it.
2. Create an admin IAM identity for deployment — IAM Identity Center (SSO) preferred, or an IAM user with access keys as fallback.
3. Configure a local profile:
   ```bash
   aws configure sso --profile <client>-prod     # or: aws configure --profile <client>-prod
   aws sts get-caller-identity --profile <client>-prod   # verify
   ```

## 2. Instantiate the template

```bash
git clone <this-template> <client>-app && cd <client>-app
./init.sh <client> --profile <client>-prod --region us-east-1
git add -A && git commit -m "chore: init <client>"
```

Name constraint: lowercase letters/digits/hyphens — it becomes stack names, S3 bucket prefixes, and SSM paths.

## 3. Bedrock model access (only if using the AI endpoint)

Bedrock models are **not** enabled by default on a new account. In the AWS console: **Bedrock → Model access → enable** the model you plan to use (default: Amazon Nova Lite). Cross-region inference profiles (`us.` prefix) also need the underlying model enabled. Skip this if you delete `api/routes/ai.py`.

## 4. Bootstrap configuration

```bash
./bootstrap.sh --env prod
```

Prompts for the model ID, signup domain allowlist (recommend restricting to the client's email domain), and optional ACM cert. The JWT secret is generated automatically and stored as a SecureString.

## 5. First deploy

```bash
./deploy.sh --env prod
```

~5-10 min on first run (CloudFront distribution creation is the slow part). The script ends with the live CloudFront URL and a Playwright smoke test against it.

**First signup on the fresh deployment becomes the admin account** — do it immediately, or restrict signups to the client's domain in step 4.

## 6. Custom domain (optional, can be added later)

1. Client buys/owns a domain (Route 53 or any registrar).
2. Request an ACM certificate **in us-east-1** for `app.<domain>` (DNS validation; add the CNAME they give you).
3. Store it: re-run `./bootstrap.sh --env prod --force` and supply the cert ARN + domain names (or `aws ssm put-parameter` directly).
4. Redeploy: `./deploy.sh --env prod`.
5. Point DNS at CloudFront: CNAME (or Route 53 alias) from `app.<domain>` to the `*.cloudfront.net` domain in the stack outputs.

Watch out: an unverified registrant email on a newly bought domain gets the domain suspended (clientHold) — verify the ICANN email promptly.

## 7. Handover notes for the client

- **Costs**: near-zero idle; usage-based beyond that. Set an AWS Budget alert (e.g. $20/mo) on day one.
- **Logs**: `sam logs --stack-name <client>-prod --tail`, or CloudWatch Logs in the console.
- **Test environment**: `./bootstrap.sh --env test && ./deploy.sh --env test` gives a full isolated copy.
- **Teardown**: empty the two S3 buckets, then `aws cloudformation delete-stack --stack-name <client>-<env>`.
