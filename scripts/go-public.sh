#!/usr/bin/env bash
# Makes the repository public and applies its GitHub security settings.
# Usage: scripts/go-public.sh OWNER/REPO
#        REQUIRED_CHECKS="dependency-review CodeQL" scripts/go-public.sh OWNER/REPO
# Safe to re-run: every step checks or overwrites state instead of adding to it.
# Rulesets need a public repo on the Free plan, so they come after the visibility change.
set -euo pipefail

REPO="${1:?usage: $0 OWNER/REPO}"
REQUIRED_CHECKS="${REQUIRED_CHECKS:-}" # space-separated status check names; empty: none

step() { printf '\n==> %s\n' "$*"; }
die() {
	printf 'error: %s\n' "$*" >&2
	exit 1
}

step "Checking tools"
command -v gh >/dev/null || die "gh is not installed"
command -v jq >/dev/null || die "jq is not installed"
gh auth status >/dev/null 2>&1 || die "gh is not logged in"
gh repo edit --help | grep -q -- '--accept-visibility-change-consequences' ||
	die "gh $(gh --version | head -1 | awk '{print $3}') is too old: upgrade gh (needs repo edit --accept-visibility-change-consequences and gh ruleset)"
gh ruleset --help >/dev/null 2>&1 || die "gh has no 'ruleset' command: upgrade gh"

step "1. Visibility"
visibility="$(gh repo view "$REPO" --json visibility --jq .visibility)"
if [[ "$visibility" == "PUBLIC" ]]; then
	echo "already public"
else
	gh repo edit "$REPO" --visibility public --accept-visibility-change-consequences
	echo "now public"
fi

step "2. Merge settings, wiki and projects"
gh repo edit "$REPO" --enable-squash-merge --enable-merge-commit=false \
	--enable-rebase-merge=false --delete-branch-on-merge
echo "squash merge only; branches deleted on merge"
if [[ "$(gh api "repos/$REPO" --jq .has_wiki)" == "true" ]]; then
	if git ls-remote --exit-code "https://github.com/$REPO.wiki.git" >/dev/null 2>&1; then
		echo "wiki has pages: left enabled"
	else
		gh repo edit "$REPO" --enable-wiki=false
		echo "wiki was empty: disabled"
	fi
else
	echo "wiki already disabled"
fi
if [[ "$(gh api "repos/$REPO" --jq .has_projects)" == "true" ]]; then
	owner="${REPO%%/*}" name="${REPO#*/}"
	# shellcheck disable=SC2016 # GraphQL variables, not shell
	query='query($o:String!,$n:String!){repository(owner:$o,name:$n){projectsV2(first:1){totalCount}}}'
	if projects="$(gh api graphql -f query="$query" -f o="$owner" -f n="$name" \
		--jq .data.repository.projectsV2.totalCount 2>/dev/null)"; then
		if [[ "$projects" == "0" ]]; then
			gh repo edit "$REPO" --enable-projects=false
			echo "no projects: disabled"
		else
			echo "$projects linked project(s): left enabled"
		fi
	else
		echo "could not list projects (token needs read:project): left enabled"
	fi
else
	echo "projects already disabled"
fi

step "3. Secret scanning and push protection"
jq -n '{security_and_analysis: {
	secret_scanning: {status: "enabled"},
	secret_scanning_push_protection: {status: "enabled"}}}' |
	gh api -X PATCH "repos/$REPO" --input - --jq .security_and_analysis

step "4. Dependabot alerts and fixes, private vulnerability reporting, immutable releases"
for endpoint in vulnerability-alerts automated-security-fixes private-vulnerability-reporting \
	immutable-releases; do
	gh api -X PUT "repos/$REPO/$endpoint" --silent
	echo "$endpoint: enabled"
done

step "5. Code scanning default setup"
gh api -X PATCH "repos/$REPO/code-scanning/default-setup" -f state=configured --silent
echo "default setup requested (runs its first analysis in the background)"

step "6. Actions permissions"
gh api -X PUT "repos/$REPO/actions/permissions/workflow" \
	-f default_workflow_permissions=read -F can_approve_pull_request_reviews=false --silent
echo "default GITHUB_TOKEN: read; Actions cannot approve pull requests"
if out="$(gh api -X PUT "repos/$REPO/actions/permissions/fork-pr-contributor-approval" \
	-f approval_policy=all_external_contributors --silent 2>&1)"; then
	echo "fork PR workflows need approval for all external contributors"
elif grep -q 'HTTP 404' <<<"$out"; then
	echo "fork PR approval API not available: set it in Settings > Actions > General >"
	echo "  'Approval for running fork pull request workflows from contributors' >"
	echo "  'Require approval for all external contributors'"
else
	die "fork PR approval: $out"
fi

step "7. Rulesets"
existing="$(gh api "repos/$REPO/rulesets" --jq '.[].name')"
if grep -qx 'main' <<<"$existing"; then
	echo "ruleset 'main' exists: skipped"
else
	# shellcheck disable=SC2086 # split REQUIRED_CHECKS into words on purpose
	checks="$(jq -nc '$ARGS.positional | map({context: .})' --args $REQUIRED_CHECKS)"
	jq -n --argjson checks "$checks" '{
		name: "main", target: "branch", enforcement: "active",
		conditions: {ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}},
		rules: ([
			{type: "deletion"},
			{type: "non_fast_forward"},
			{type: "pull_request", parameters: {
				required_approving_review_count: 0,
				dismiss_stale_reviews_on_push: false,
				require_code_owner_review: false,
				require_last_push_approval: false,
				required_review_thread_resolution: false,
				allowed_merge_methods: ["squash"]}}
		] + (if ($checks | length) > 0 then [{type: "required_status_checks", parameters: {
				strict_required_status_checks_policy: false,
				required_status_checks: $checks}}] else [] end))}' |
		gh api -X POST "repos/$REPO/rulesets" --input - --silent
	echo "ruleset 'main' created (required checks: ${REQUIRED_CHECKS:-none})"
fi
if grep -qx 'release-tags' <<<"$existing"; then
	echo "ruleset 'release-tags' exists: skipped"
else
	jq -n '{
		name: "release-tags", target: "tag", enforcement: "active",
		conditions: {ref_name: {include: ["refs/tags/v*"], exclude: []}},
		rules: [{type: "deletion"}, {type: "non_fast_forward"}]}' |
		gh api -X POST "repos/$REPO/rulesets" --input - --silent
	echo "ruleset 'release-tags' created"
fi

step "8. Verify"
echo "security_and_analysis:"
gh api "repos/$REPO" --jq .security_and_analysis
echo "rulesets:"
gh ruleset list -R "$REPO"
echo "workflow permissions:"
gh api "repos/$REPO/actions/permissions/workflow"
