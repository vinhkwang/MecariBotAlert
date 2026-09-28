#!/usr/bin/env bash
set -uo pipefail

payload="$(cat)"

extract_command() {
  printf '%s' "$payload" | python3 -c '
import json
import sys

try:
    print(json.load(sys.stdin).get("tool_input", {}).get("command", ""))
except Exception:
    print("")
' 2>/dev/null || printf ''
}

block() {
  printf 'BLOCKED by .claude/hooks/guard-git.sh\n\n%s\n\nSee CLAUDE.md section 3.1 and section 4.\n' "$1" >&2
  exit 2
}

command_text="$(extract_command)"
[[ -z "${command_text}" ]] && exit 0

current_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || printf 'unknown')"

case "${command_text}" in
  *"git merge"*)
    block "The agent never merges. Push the branch, then stop for human review." ;;
  *"gh pr merge"*)
    block "The agent never merges a pull request. That is the human's decision." ;;
  *"git push --force"*|*"git push -f "*)
    block "Force push is not allowed on a branch under review." ;;
  *"git reset --hard"*)
    block "Hard reset discards work another session may depend on. Use git revert or ask." ;;
  *"docker compose down -v"*|*"docker-compose down -v"*)
    block "The -v flag deletes the listings volume and the whole dedup database." ;;
esac

if [[ "${current_branch}" == "main" || "${current_branch}" == "master" ]]; then
  case "${command_text}" in
    *"git commit"*)
      block "Currently on ${current_branch}. Every task gets its own branch: create one first." ;;
  esac
fi

exit 0
