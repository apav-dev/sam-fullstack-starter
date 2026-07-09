#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# init.sh — one-time template instantiation.
#
# Rewrites the placeholder project prefix "myapp" to your project name across
# every tracked file, and sets the AWS profile/region defaults in the scripts.
#
# Usage:
#   ./init.sh <project-name> [--profile <aws-profile>] [--region <aws-region>]
#
# <project-name> must be lowercase letters, digits, and hyphens (it becomes
# CloudFormation stack names, S3 bucket prefixes, and SSM paths).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PLACEHOLDER="myapp"
PROFILE="default"
REGION="us-east-1"

usage() { grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

[[ $# -ge 1 ]] || usage
NAME="$1"; shift
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --region)  REGION="$2";  shift 2 ;;
    *) usage ;;
  esac
done

GREEN='\033[0;32m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()  { echo -e "${GREEN}✔ $*${NC}"; }
die() { echo -e "${RED}✖ $*${NC}"; exit 1; }

# Guards
[[ "$NAME" =~ ^[a-z][a-z0-9-]{1,30}$ ]] \
  || die "Project name must match [a-z][a-z0-9-]{1,30} (used in bucket/stack names). Got: '$NAME'"
[[ "$NAME" != "$PLACEHOLDER" ]] || die "Pick a name other than the placeholder itself."

cd "$(dirname "${BASH_SOURCE[0]}")"

FILES=$(git ls-files | xargs grep -l "$PLACEHOLDER" 2>/dev/null || true)
[[ -n "$FILES" ]] || die "No '$PLACEHOLDER' occurrences found — init.sh has already been run."

echo -e "${CYAN}Renaming '$PLACEHOLDER' → '$NAME' (profile: $PROFILE, region: $REGION)${NC}"

for f in $FILES; do
  # BSD/GNU-sed portable in-place edit
  sed -i.initbak "s/${PLACEHOLDER}/${NAME}/g" "$f" && rm -f "$f.initbak"
done
ok "Rewrote project name in $(echo "$FILES" | wc -l | tr -d ' ') files"

for script in deploy.sh bootstrap.sh; do
  sed -i.initbak \
    -e "s/^AWS_PROFILE=\"\${AWS_PROFILE_OVERRIDE:-default}\"/AWS_PROFILE=\"\${AWS_PROFILE_OVERRIDE:-${PROFILE}}\"/" \
    -e "s/^AWS_REGION=\"us-east-1\"/AWS_REGION=\"${REGION}\"/" \
    "$script" && rm -f "$script.initbak"
done
ok "Set AWS profile/region defaults in deploy.sh and bootstrap.sh"

# This script is single-use; remove it from the instantiated project.
rm -- "$0"
ok "Removed init.sh (single-use)"

echo ""
echo "Next steps:"
echo "  1. Review the diff:        git diff"
echo "  2. Commit:                 git add -A && git commit -m 'chore: init ${NAME}'"
echo "  3. Create SSM parameters:  ./bootstrap.sh --env prod"
echo "  4. Deploy:                 ./deploy.sh --env prod"
