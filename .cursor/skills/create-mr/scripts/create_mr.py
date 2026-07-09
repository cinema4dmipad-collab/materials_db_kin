#!/usr/bin/env python3
"""Create or update GitLab MR for current branch using deterministic flow."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TRIVIAL_TITLE_RE = re.compile(r"^(chore|style|fix\(typo\))")


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def try_git(*args: str) -> Optional[str]:
    try:
        return run_git(*args)
    except subprocess.CalledProcessError:
        return None


def parse_remote(remote_url: str) -> Tuple[str, str]:
    ssh_match = re.match(r"^[^@]+@([^:/]+):(.+?)(?:\.git)?$", remote_url)
    if ssh_match:
        return ssh_match.group(1), ssh_match.group(2)
    https_match = re.match(r"^[a-zA-Z]+://([^/]+)/(.+?)(?:\.git)?$", remote_url)
    if https_match:
        return https_match.group(1), https_match.group(2)
    raise RuntimeError(f"Unsupported origin URL format: {remote_url}")


def load_glab_token(host: str) -> str:
    cfg_path = Path.home() / ".config" / "glab-cli" / "config.yml"
    if not cfg_path.exists():
        raise RuntimeError(f"glab config not found: {cfg_path}")

    content = cfg_path.read_text(encoding="utf-8")
    in_host_block = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip("\n")
        if line.strip() == f"{host}:":
            in_host_block = True
            continue
        if in_host_block and line and not line.startswith((" ", "\t")):
            in_host_block = False
        if in_host_block and line.strip().startswith("token:"):
            token = line.split(":", 1)[1].strip()
            if token:
                return token
            break

    raise RuntimeError(f"No token found for host {host} in {cfg_path}")


def api_request(
    method: str,
    url: str,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    data = None
    headers = {"PRIVATE-TOKEN": token}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitLab API {exc.code} {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitLab API request failed for {url}: {exc}") from exc


def resolve_title(target: str, fallback_branch: str) -> str:
    last = run_git("log", "-1", "--pretty=%s")
    if not last:
        return fallback_branch
    if not TRIVIAL_TITLE_RE.search(last):
        return last

    history = try_git("log", f"{target}..HEAD", "--pretty=%s")
    if history is None and not target.startswith("origin/"):
        history = try_git("log", f"origin/{target}..HEAD", "--pretty=%s")
    if history is None:
        return fallback_branch
    for line in history.splitlines():
        if line and not TRIVIAL_TITLE_RE.search(line):
            return line
    return fallback_branch


def parse_assignee_ids(env_value: str) -> List[int]:
    ids: List[int] = []
    for item in env_value.split(","):
        item = item.strip()
        if item.isdigit():
            ids.append(int(item))
    return ids


def extract_existing_mr_iid(resp: Dict[str, Any]) -> Optional[int]:
    message = resp.get("message")
    if isinstance(message, list):
        message = message[0] if message else ""
    if not isinstance(message, str):
        return None
    match = re.search(r"!(\d+)", message)
    return int(match.group(1)) if match else None


def origin_branch_name(remote_ref: str) -> str:
    return remote_ref.removeprefix("origin/")


def remote_branch_exists(remote_ref: str) -> bool:
    return try_git("rev-parse", "--verify", "--quiet", remote_ref) is not None


def git_is_ancestor(ancestor: str, descendant: str) -> bool:
    return try_git("merge-base", "--is-ancestor", ancestor, descendant) is not None


def resolve_origin_head() -> Optional[str]:
    ref = try_git("symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if not ref:
        return None
    if ref == "origin/HEAD":
        return None
    return ref


def resolve_parent_branch(current_branch: str) -> str:
    candidates: List[str] = []
    refs = try_git(
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/remotes/origin",
    )
    if refs:
        for ref in refs.splitlines():
            if not ref or ref == "origin/HEAD":
                continue
            if origin_branch_name(ref) == current_branch:
                continue
            candidates.append(ref)

    ranked: List[Tuple[int, int, str]] = []
    for ref in candidates:
        if git_is_ancestor("HEAD", ref):
            continue
        merge_base = try_git("merge-base", "HEAD", ref)
        if not merge_base:
            continue
        timestamp_text = try_git("show", "-s", "--format=%ct", merge_base)
        distance_text = try_git("rev-list", "--count", f"{merge_base}..HEAD")
        if not timestamp_text or not distance_text:
            continue
        try:
            timestamp = int(timestamp_text)
            distance = int(distance_text)
        except ValueError:
            continue
        ranked.append((timestamp, -distance, ref))

    if ranked:
        ranked.sort(reverse=True)
        return origin_branch_name(ranked[0][2])

    origin_head = resolve_origin_head()
    if origin_head and origin_branch_name(origin_head) != current_branch:
        return origin_branch_name(origin_head)

    for branch in ("main", "master", "develop"):
        ref = f"origin/{branch}"
        if branch != current_branch and remote_branch_exists(ref):
            return branch

    raise RuntimeError(
        "Could not infer target branch. Pass --target or set MR_TARGET_BRANCH."
    )


def resolve_target_branch(cli_target: Optional[str], current_branch: str) -> str:
    if cli_target and cli_target.strip():
        return cli_target.strip()

    env_target = os.getenv("MR_TARGET_BRANCH", "").strip()
    if env_target:
        return env_target

    return resolve_parent_branch(current_branch)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create or update GitLab MR for current branch."
    )
    parser.add_argument(
        "--description-file",
        required=True,
        help="Path to Markdown file with MR description.",
    )
    parser.add_argument(
        "--title",
        default="",
        help="Optional MR title override.",
    )
    parser.add_argument(
        "--target",
        default=None,
        help=(
            "Target branch override. Defaults to MR_TARGET_BRANCH, then the "
            "inferred parent branch."
        ),
    )
    args = parser.parse_args()

    description_path = Path(args.description_file).expanduser()
    if not description_path.exists():
        raise RuntimeError(f"Description file not found: {description_path}")
    description = description_path.read_text(encoding="utf-8").strip()
    if not description:
        raise RuntimeError("Description file is empty.")

    repo_root = run_git("rev-parse", "--show-toplevel")
    os.chdir(repo_root)

    branch = run_git("branch", "--show-current")
    if not branch:
        raise RuntimeError("Could not resolve current branch.")
    target = resolve_target_branch(args.target, branch)

    # Deterministic flow: always push branch with upstream before MR API calls.
    subprocess.run(["git", "push", "-u", "origin", branch], check=True)

    remote = run_git("remote", "get-url", "origin")
    host, project_path = parse_remote(remote)
    encoded_project = urllib.parse.quote(project_path, safe="")
    token = load_glab_token(host)

    api_base = f"https://{host}/api/v4"

    project = api_request("GET", f"{api_base}/projects/{encoded_project}", token)
    project_id = project.get("id")
    if not project_id:
        raise RuntimeError("Failed to resolve project ID from GitLab API.")

    title = args.title.strip() or resolve_title(target, branch)

    assignee_ids: List[int] = []
    env_assignees = os.getenv("MR_ASSIGNEE_IDS", "").strip()
    if env_assignees:
        assignee_ids = parse_assignee_ids(env_assignees)
    elif os.getenv("MR_ASSIGN_SELF", "true").lower() != "false":
        me = api_request("GET", f"{api_base}/user", token)
        if isinstance(me.get("id"), int):
            assignee_ids = [me["id"]]

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
            raise RuntimeError(f"Unexpected create MR response: {json.dumps(created)}")

    except RuntimeError as exc:
        text = str(exc)
        match = re.search(r"!([0-9]+)", text)
        if not match:
            raise
        iid = int(match.group(1))

    updated = api_request(
        "PUT",
        f"{api_base}/projects/{project_id}/merge_requests/{iid}",
        token,
        payload=payload,
    )
    web_url = updated.get("web_url")
    if not web_url:
        raise RuntimeError(f"Failed to update MR !{iid}: {json.dumps(updated)}")

    print(web_url)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
