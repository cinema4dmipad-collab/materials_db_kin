---
name: glab-mr-create
description: Creates a GitLab merge request via curl (glab mr create fails on self-managed GitLab with unmarshal error). Runs mr-diff to get template and diff, fills the template with AI, then creates MR via GitLab API. Use when the user wants to create an MR, open merge request, or push and create MR.
---

# glab MR create

Creates a merge request by generating description from diff and calling GitLab API via curl.

## Workflow

1. **Run mr-diff** (from repo root or any dir inside repo):
   ```bash
   ~/.cursor/skills/gitlab-mr-description/scripts/mr-diff.sh
   ```

2. **Fill the template** with description based on the diff. If diff is empty, tell the user there are no changes and do not create MR.

3. **Push branch** if not yet pushed: `git push -u origin $(git branch --show-current)`.

4. **Determine title** from the last commit or branch name:
   ```bash
   git log -1 --pretty=%s
   ```
   Or `git branch --show-current` if commit message is unsuitable.

5. **Create MR** via GitLab API (glab mr create fails on self-managed GitLab with unmarshal error):
   ```bash
   HOST=$(git remote get-url origin | sed -n 's/.*@\([^:/]*\).*/\1/p')
   TOKEN=$(grep -A5 "${HOST}:" ~/.config/glab-cli/config.yml 2>/dev/null | grep 'token:' | head -1 | awk '{print $2}')
   PROJECT_ID=$(find ~/.config/glab-cli/recover -name mr.json -mmin -60 -exec jq -r '.source_project.id // empty' {} \; 2>/dev/null | head -1)
   [ -z "$PROJECT_ID" ] && PROJECT_ID=$(curl -s -H "PRIVATE-TOKEN: $TOKEN" "https://${HOST}/api/v4/projects/$(git remote get-url origin | sed -n 's/.*:\(.*\)\.git/\1/p' | sed 's/\//%2F/g')" | jq -r '.id')
   curl -s -X POST "https://${HOST}/api/v4/projects/${PROJECT_ID}/merge_requests" \
     -H "PRIVATE-TOKEN: $TOKEN" \
     -H "Content-Type: application/json" \
     -d "{\"source_branch\":\"$(git branch --show-current)\",\"target_branch\":\"develop\",\"title\":\"Title\",\"description\":\"Description\"}"
   ```
   Extract `web_url` from the JSON response. For multiline description, escape newlines as `\n` in the JSON string. Alternative: `glab mr create --fill --web` opens the pre-filled form in browser.

6. **Confirm** — curl returns JSON with `web_url`; output the MR link to the user.

## Notes

- Repository must be a GitLab project with glab authenticated (token in config used for API).
- Template: `.gitlab/merge_request_templates/Default.md` (when present).
- mr-diff excludes `poetry.lock` and similar from the diff.
