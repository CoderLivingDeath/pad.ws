#!/usr/bin/env bash
set -euo pipefail

root="${1:-.github}"
status=0
found=0

while IFS= read -r entry; do
  file="${entry%%:*}"
  rest="${entry#*:}"
  line="${rest%%:*}"
  content="${rest#*:}"
  ref="$(printf '%s' "$content" | sed -E 's/^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*//; s/[[:space:]]+#.*$//; s/[[:space:]]+$//')"
  found=1

  case "$ref" in
    ./*)
      ;;
    docker://*)
      if [[ ! "$ref" =~ @sha256:[0-9a-f]{64}$ ]]; then
        printf '%s:%s: docker image must be pinned by digest: %s\n' "$file" "$line" "$ref" >&2
        status=1
      fi
      ;;
    *@*)
      sha="${ref##*@}"
      if [[ ! "$sha" =~ ^[0-9a-f]{40}$ ]]; then
        printf '%s:%s: action must be pinned to a 40-character commit SHA: %s\n' "$file" "$line" "$ref" >&2
        status=1
      fi
      ;;
    *)
      printf '%s:%s: missing @<commit-sha>: %s\n' "$file" "$line" "$ref" >&2
      status=1
      ;;
  esac
done < <(grep -RInE '^[[:space:]]*(-[[:space:]]+)?uses:[[:space:]]*' "$root" || true)

if [[ "$found" -eq 0 ]]; then
  echo "No uses: entries found under $root" >&2
  exit 1
fi

if [[ "$status" -ne 0 ]]; then
  cat >&2 <<'EOF'
Pin every action to a full 40-character commit SHA and keep the release in a comment:

  uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
EOF
fi

exit "$status"
