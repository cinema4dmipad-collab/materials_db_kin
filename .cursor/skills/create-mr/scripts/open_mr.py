#!/usr/bin/env python3
"""Open GitLab MR for the current branch in the default browser."""

import os
import re
import subprocess
import sys
import webbrowser
from typing import Optional, Tuple

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


def get_git_remote_url():
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def get_current_branch():
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def parse_host_and_project(url: str) -> Tuple[str, str]:
    # git@host:group/project.git or https://host/group/project.git
    host = ""
    if "@" in url:
        m = re.search(r"@([^:/]+)[:/](.+?)\.git$", url)
        if m:
            host, path = m.groups()
            path = path.replace("/", "%2F")
    else:
        m = re.search(r"://([^/]+)/(.+?)\.git$", url)
        if m:
            host, path = m.groups()
            path = path.replace("/", "%2F")
    return host, path


def get_token(host: str) -> Optional[str]:
    config_path = os.path.expanduser("~/.config/glab-cli/config.yml")
    if not os.path.exists(config_path):
        return None
    with open(config_path) as f:
        content = f.read()
    # Look for host block and token
    in_block = False
    for line in content.splitlines():
        if f"{host}:" in line:
            in_block = True
            continue
        if in_block:
            if line.strip().startswith("token:"):
                return line.split(":", 1)[1].strip()
            if line and not line.startswith(" "):
                in_block = False
    return None


def main():
    # Ensure we're in repo root (works when run from any dir inside repo)
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Not a git repository", file=sys.stderr)
        sys.exit(1)
    os.chdir(result.stdout.strip())

    url = get_git_remote_url()
    host, proj_path = parse_host_and_project(url)
    if not host or not proj_path:
        print("Could not parse remote URL", file=sys.stderr)
        sys.exit(1)

    branch = get_current_branch()
    token = get_token(host)
    if not token:
        print("No glab token found for", host, file=sys.stderr)
        sys.exit(1)

    api_base = f"https://{host}/api/v4"
    headers = {"PRIVATE-TOKEN": token}

    # Get project ID
    r = requests.get(f"{api_base}/projects/{proj_path}", headers=headers, timeout=10)
    if not r.ok:
        print("Failed to get project:", r.text, file=sys.stderr)
        sys.exit(1)
    project_id = r.json().get("id")

    # Find MR for current branch (state=opened)
    r = requests.get(
        f"{api_base}/projects/{project_id}/merge_requests",
        headers=headers,
        params={"source_branch": branch, "state": "opened"},
        timeout=10,
    )
    if not r.ok:
        print("Failed to list MRs:", r.text, file=sys.stderr)
        sys.exit(1)

    mrs = r.json()
    if not mrs:
        print(f"No open MR for branch '{branch}'", file=sys.stderr)
        sys.exit(1)

    web_url = mrs[0].get("web_url")
    if not web_url:
        print("MR has no web_url", file=sys.stderr)
        sys.exit(1)

    print(web_url)
    webbrowser.open(web_url)


if __name__ == "__main__":
    main()
