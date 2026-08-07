---
name: gitlab-mr-description
description: Runs mr-diff script and fulfills its prompt to create GitLab MR description. Use when the user wants to fill an MR by template, write merge request summary, or mr-diff.
---

# GitLab MR description

1. Run the script (from repo root or any dir inside repo):
   ```bash
   ~/.cursor/skills/gitlab-mr-description/scripts/mr-diff.sh
   ```
2. Treat the script output as the prompt and do what it asks: create the MR summary by the template and the diff.

3. If diff is empty, answer that is no changes to describe!
