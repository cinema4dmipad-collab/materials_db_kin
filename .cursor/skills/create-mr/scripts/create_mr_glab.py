#!/usr/bin/env python3
"""Create GitLab MR using origin-glab remote (materials_db_v1 policy)."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REMOTE = "origin-glab"
HOST = "gitlab.keeneticcorp.ru"
PROJECT_PATH = "development/applications/materials_db_strict"


def load_token(host: str) -> str:
    cfg_path = Path.home() / ".config" / "glab-cli" / "config.yml"
    content = cfg_path.read_text(encoding="utf-8")
    in_block = False
    for line in content.splitlines():
        if line.strip() == f"{host}:":
            in_block = True
            continue
        if in_block and line and not line.startswith((" ", "\t")):
            in_block = False
        if in_block and line.strip().startswith("token:"):
            token = line.split(":", 1)[1].strip()
            if token:
                return token
    raise RuntimeError(f"No token for {host} in {cfg_path}")


def api_request(method: str, url: str, token: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    data = None
    headers = {"PRIVATE-TOKEN": token}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitLab API {exc.code} {url}: {body}") from exc


def extract_existing_mr_iid(resp: Dict[str, Any]) -> Optional[int]:
    message = resp.get("message")
    if isinstance(message, list):
        message = message[0] if message else ""
    if not isinstance(message, str):
        return None
    match = re.search(r"!(\d+)", message)
    return int(match.group(1)) if match else None


def main() -> int:
    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    root = Path(repo_root)
    description = (root / "mr_description.md").read_text(encoding="utf-8").strip()
    if not description:
        raise RuntimeError("mr_description.md is empty")

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = "develop"
    title = "feat(workspaces): material links, create-from-template, and shared sample access"

    subprocess.run(["git", "push", "-u", REMOTE, branch], check=True)

    token = load_token(HOST)
    encoded_project = urllib.parse.quote(PROJECT_PATH, safe="")
    api_base = f"https://{HOST}/api/v4"
    project = api_request("GET", f"{api_base}/projects/{encoded_project}", token)
    project_id = project["id"]

    me = api_request("GET", f"{api_base}/user", token)
    assignee_ids: List[int] = [me["id"]] if isinstance(me.get("id"), int) else []

    payload: Dict[str, Any] = {
        "source_branch": branch,
        "target_branch": target,
        "title": title,
        "description": description,
    }
    if assignee_ids:
        payload["assignee_ids"] = assignee_ids

    create_url = f"{api_base}/projects/{project_id}/merge_requests"
    try:
        created = api_request("POST", create_url, token, payload=payload)
        web_url = created.get("web_url")
        if web_url:
            print(web_url)
            return 0
        iid = extract_existing_mr_iid(created)
        if iid is None:
            raise RuntimeError(json.dumps(created))
    except RuntimeError as exc:
        match = re.search(r"!(\d+)", str(exc))
        if not match:
            raise
        iid = int(match.group(1))

    updated = api_request(
        "PUT",
        f"{api_base}/projects/{project_id}/merge_requests/{iid}",
        token,
        payload=payload,
    )
    print(updated["web_url"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
