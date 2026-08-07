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


def api_request(method: str, url: str, token: str, payload: Optional[Dict[str, Any]] = None) -> Any:
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


def find_open_mr_iid(api_base: str, project_id: int, token: str, source: str, target: str) -> Optional[int]:
    query = urllib.parse.urlencode(
        {
            "state": "opened",
            "source_branch": source,
            "target_branch": target,
            "per_page": "20",
        }
    )
    listed = api_request(
        "GET",
        f"{api_base}/projects/{project_id}/merge_requests?{query}",
        token,
    )
    if not isinstance(listed, list) or not listed:
        return None
    iid = listed[0].get("iid")
    return int(iid) if isinstance(iid, int) else None


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Create/update GitLab MR via origin-glab.")
    parser.add_argument("--description-file", default="mr_description.md")
    parser.add_argument("--title", required=True)
    parser.add_argument("--target", default="develop")
    args = parser.parse_args()

    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    root = Path(repo_root)
    description_path = Path(args.description_file)
    if not description_path.is_absolute():
        description_path = root / description_path
    description = description_path.read_text(encoding="utf-8").strip()
    if not description:
        raise RuntimeError(f"{description_path} is empty")

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target = args.target.strip() or "develop"
    title = args.title.strip()

    subprocess.run(["git", "push", "-u", REMOTE, branch], check=True)

    token = load_token(HOST)
    encoded_project = urllib.parse.quote(PROJECT_PATH, safe="")
    api_base = f"https://{HOST}/api/v4"
    project = api_request("GET", f"{api_base}/projects/{encoded_project}", token)
    project_id = project["id"]

    me = api_request("GET", f"{api_base}/user", token)
    assignee_ids: List[int] = [me["id"]] if isinstance(me.get("id"), int) else []

    update_payload: Dict[str, Any] = {
        "title": title,
        "description": description,
    }
    if assignee_ids:
        update_payload["assignee_ids"] = assignee_ids

    existing_iid = find_open_mr_iid(api_base, project_id, token, branch, target)
    if existing_iid is not None:
        updated = api_request(
            "PUT",
            f"{api_base}/projects/{project_id}/merge_requests/{existing_iid}",
            token,
            payload=update_payload,
        )
        print(updated["web_url"])
        return 0

    create_payload: Dict[str, Any] = {
        "source_branch": branch,
        "target_branch": target,
        **update_payload,
    }
    create_url = f"{api_base}/projects/{project_id}/merge_requests"
    try:
        created = api_request("POST", create_url, token, payload=create_payload)
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
        payload=update_payload,
    )
    print(updated["web_url"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
