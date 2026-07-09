#!/usr/bin/env python3
"""
TestRay TMS: four saved filters + project-scoped «panel» URLs (issue navigator in this project).

By default DOES NOT create Jira Agile boards (those open global Software context — easy to jump to another project like LUS01). Use optional --with-boards only if you really need Kanban.

Steps (default): POST /rest/api/2/filter (sharePermissions: project) — then URLs:
  {JIRA_URL}/projects/{KEY}/issues?filter={id}

With --with-boards (or existing board_id in state), docs also list Rapid Kanban URLs:
  {JIRA_URL}/secure/RapidBoard.jspa?rapidView=<board_id>[&selectedIssue=KEY-N]

Important: a Rapid Board URL is not enough. Jira creates default Kanban
columns (e.g. To do / In progress / Done).

This script does **not** create, edit, or migrate Jira **statuses** or **workflows**;
that stays in Project settings / Workflow schemes. Optional
`--configure-board-columns` can push a 1:1 column mapping derived from
`GET /rest/api/2/project/{KEY}/statuses` (off by default). If every issue type
still shares one workflow in Jira, that API legitimately returns the same
status list for each type until you separate workflows manually.

Environment (same as MCP):
  JIRA_URL              Base URL without trailing slash
  JIRA_PERSONAL_TOKEN   Bearer PAT

Idempotency: --state-file (default docs/tms.panels.state.json).

Usage:
  export JIRA_URL=... JIRA_PERSONAL_TOKEN=...
  python3 jira_create_testray_boards.py --project-key KNX --write-panels-doc docs/tms.panels.md

Legacy Agile boards:
  ... --with-boards
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlencode
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Facet:
    slug: str
    panel_label_ru: str  # Display name for humans / optional board title
    issue_type: str  # Exact Jira issuetype string


FACETS: tuple[Facet, ...] = (
    Facet("requirements", "Требования", "Functional Requirement"),
    Facet("test_cases", "Тест-кейсы", "Test Case"),
    Facet("defects", "Дефекты", "Defect"),
    Facet("test_plans", "Тест-планы", "Test Plan"),
)

class JiraClient:
    def __init__(self, base_url: str, token: str, insecure_tls: bool) -> None:
        self.base = base_url.rstrip("/")
        self.token = token
        ctx = None
        if insecure_tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        self.ssl_ctx = ctx

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        url = f"{self.base}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if payload is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60, context=self.ssl_ctx) as resp:
                body = resp.read().decode("utf-8")
                status = resp.status
                parsed: Any
                if body.strip():
                    try:
                        parsed = json.loads(body)
                    except json.JSONDecodeError:
                        parsed = body
                else:
                    parsed = {}
                return status, parsed
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8") if err.fp else ""
            try:
                detail = json.loads(raw) if raw.strip() else {"raw": raw}
            except json.JSONDecodeError:
                detail = {"raw": raw}
            return err.code, detail

    def get_project(self, project_key: str) -> dict[str, Any]:
        status, body = self._request("GET", f"/rest/api/2/project/{project_key.upper()}")
        if status != 200 or not isinstance(body, dict):
            raise RuntimeError(f"GET project {project_key}: HTTP {status} {body}")
        return body

    def get_project_statuses(self, project_key: str) -> dict[str, list[dict[str, Any]]]:
        status, body = self._request("GET", f"/rest/api/2/project/{project_key.upper()}/statuses")
        if status != 200 or not isinstance(body, list):
            raise RuntimeError(f"GET project statuses {project_key}: HTTP {status} {body}")
        result: dict[str, list[dict[str, Any]]] = {}
        for issue_type in body:
            if not isinstance(issue_type, dict) or not issue_type.get("name"):
                continue
            statuses = issue_type.get("statuses", [])
            if isinstance(statuses, list):
                result[str(issue_type["name"])] = [s for s in statuses if isinstance(s, dict) and s.get("name")]
        return result

    def get_filter(self, filter_id: int) -> dict[str, Any] | None:
        status, body = self._request("GET", f"/rest/api/2/filter/{filter_id}")
        if status == 200 and isinstance(body, dict):
            return body
        return None

    def create_filter(self, name: str, jql: str, project_nid: str) -> dict[str, Any]:
        payload = {
            "name": name,
            "jql": jql,
            "sharePermissions": [{"type": "project", "project": {"id": project_nid}}],
        }
        status, body = self._request("POST", "/rest/api/2/filter", payload=payload)
        if 200 <= status < 300 and isinstance(body, dict):
            return body
        raise RuntimeError(f"Create filter '{name}': HTTP {status} {body}")

    def delete_filter(self, filter_id: int) -> bool:
        status, body = self._request("DELETE", f"/rest/api/2/filter/{filter_id}")
        if status in (200, 202, 204, 404):
            return status != 404
        raise RuntimeError(f"Delete filter {filter_id}: HTTP {status} {body}")

    def get_boards(self, project_key: str, board_type: str = "kanban") -> list[dict[str, Any]]:
        boards: list[dict[str, Any]] = []
        start_at = 0
        while True:
            status, body = self._request(
                "GET",
                f"/rest/agile/1.0/board?projectKeyOrId={project_key}&type={board_type}&startAt={start_at}&maxResults=50",
            )
            if status != 200 or not isinstance(body, dict):
                raise RuntimeError(f"List boards for {project_key}: HTTP {status} {body}")
            values = body.get("values", [])
            if isinstance(values, list):
                boards.extend([b for b in values if isinstance(b, dict)])
            if body.get("isLast", True):
                break
            start_at = int(body.get("startAt", start_at)) + int(body.get("maxResults", 50))
        return boards

    def get_board(self, board_id: int) -> dict[str, Any] | None:
        status, body = self._request("GET", f"/rest/agile/1.0/board/{board_id}")
        if status == 200 and isinstance(body, dict):
            return body
        return None

    def delete_board(self, board_id: int) -> bool:
        status, body = self._request("DELETE", f"/rest/agile/1.0/board/{board_id}")
        if status in (200, 202, 204, 404):
            return status != 404
        raise RuntimeError(f"Delete board {board_id}: HTTP {status} {body}")

    def get_board_edit_model(self, board_id: int) -> dict[str, Any] | None:
        status, body = self._request(
            "GET",
            f"/rest/greenhopper/1.0/rapidviewconfig/editmodel?rapidViewId={board_id}",
        )
        if status == 200 and isinstance(body, dict):
            return body
        return None

    def create_board(self, title: str, filter_id: int) -> dict[str, Any]:
        payload = {"name": title, "type": "kanban", "filterId": filter_id}
        status, body = self._request("POST", "/rest/agile/1.0/board", payload=payload)
        if 200 <= status < 300 and isinstance(body, dict):
            return body
        raise RuntimeError(f"Create board '{title}' from filter {filter_id}: HTTP {status} {body}")

    def configure_board_columns(self, board_id: int, expected_statuses: list[dict[str, Any]]) -> dict[str, Any]:
        edit_model = self.get_board_edit_model(board_id)
        if edit_model is None:
            raise RuntimeError(f"GET rapidview editmodel {board_id}: no data")
        rapid_list = edit_model.get("rapidListConfig")
        if not isinstance(rapid_list, dict):
            raise RuntimeError(f"Board {board_id}: rapidListConfig missing")

        statuses_by_name: dict[str, dict[str, Any]] = {}
        for key in ("mappedColumns",):
            for col in rapid_list.get(key, []) or []:
                if not isinstance(col, dict):
                    continue
                for status in col.get("mappedStatuses", []) or []:
                    if isinstance(status, dict) and status.get("name"):
                        statuses_by_name[str(status["name"])] = status
        for status in rapid_list.get("unmappedStatuses", []) or []:
            if isinstance(status, dict) and status.get("name"):
                statuses_by_name[str(status["name"])] = status

        expected_names = status_names(expected_statuses)
        missing = [name for name in expected_names if name not in statuses_by_name]
        if missing:
            raise RuntimeError(f"Board {board_id}: statuses absent from workflow: {', '.join(missing)}")

        mapped_columns = rapid_list.get("mappedColumns", [])
        kanplan = next(
            (col for col in mapped_columns if isinstance(col, dict) and col.get("isKanPlanColumn")),
            {"name": "Список задач", "min": "", "max": "", "mappedStatuses": [], "isKanPlanColumn": True},
        )
        new_columns: list[dict[str, Any]] = [
            {
                **({"id": kanplan["id"]} if "id" in kanplan else {}),
                "name": str(kanplan.get("name", "Список задач")),
                "min": str(kanplan.get("min", "")),
                "max": str(kanplan.get("max", "")),
                "mappedStatuses": [],
                "isKanPlanColumn": True,
            }
        ]
        for status_name in expected_names:
            new_columns.append(
                {
                    "name": status_name,
                    "min": "",
                    "max": "",
                    "mappedStatuses": [statuses_by_name[status_name]],
                    "isKanPlanColumn": False,
                }
            )

        payload = {
            "rapidViewId": board_id,
            "mappedColumns": new_columns,
            "currentStatisticsField": rapid_list.get("currentStatisticsField"),
            "showDaysInColumn": rapid_list.get("showDaysInColumn", False),
        }
        status, body = self._request(
            "PUT",
            "/rest/greenhopper/1.0/rapidviewconfig/columns",
            payload=payload,
        )
        if 200 <= status < 300 and isinstance(body, dict):
            return body
        raise RuntimeError(f"Configure board columns {board_id}: HTTP {status} {body}")


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "items": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items")
    if not isinstance(items, dict):
        raise ValueError("state file schema: items dict required")
    return {"schema_version": data.get("schema_version", 1), "items": items}


def save_state(path: Path, *, project_key: str, base_url: str, items: dict[str, Any]) -> None:
    blob = {"schema_version": 1, "project_key": project_key, "base_url": base_url, "items": items}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")


def filter_name(project_key: str, slug: str) -> str:
    return f"{project_key} TMS panel [{slug}]"


def facet_jql(project_key: str, issue_type: str) -> str:
    return (
        f'project = {project_key} AND issuetype = "{issue_type}" '
        "ORDER BY Rank ASC, updated DESC"
    )


def merge_item(items: dict[str, Any], slug: str) -> dict[str, Any]:
    cur = items.get(slug)
    if isinstance(cur, dict):
        return dict(cur)
    return {}


def status_names(statuses: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for status in statuses:
        name = status.get("name")
        if name:
            names.append(str(name))
    return names


def panel_issues_url(base: str, project_key: str, filter_id: int) -> str:
    return f"{base.rstrip('/')}/projects/{project_key}/issues?filter={filter_id}"


def rapid_board_url(base: str, board_id: int, *, selected_issue: str | None = None) -> str:
    """Classic Jira Software URL; rapidView matches Agile REST board id."""
    origin = base.rstrip("/")
    q: dict[str, str] = {"rapidView": str(board_id)}
    if selected_issue and selected_issue.strip():
        q["selectedIssue"] = selected_issue.strip()
    return f"{origin}/secure/RapidBoard.jspa?{urlencode(q)}"


def board_column_mapping(edit_model: dict[str, Any]) -> list[tuple[str, list[str]]]:
    cols = edit_model.get("rapidListConfig", {}).get("mappedColumns", [])
    result: list[tuple[str, list[str]]] = []
    if not isinstance(cols, list):
        return result
    for col in cols:
        if not isinstance(col, dict):
            continue
        statuses = []
        for st in col.get("mappedStatuses", []) or []:
            if isinstance(st, dict) and st.get("name"):
                statuses.append(str(st["name"]))
        result.append((str(col.get("name", "")), statuses))
    return result


def board_columns_match_statuses(edit_model: dict[str, Any], expected_status_names: list[str]) -> bool:
    mapping = board_column_mapping(edit_model)
    active = [(name, statuses) for name, statuses in mapping if statuses]
    if len(active) != len(expected_status_names):
        return False
    return all(name == expected and statuses == [expected] for (name, statuses), expected in zip(active, expected_status_names))


def board_column_warning(edit_model: dict[str, Any], expected_status_names: list[str]) -> str | None:
    if board_columns_match_statuses(edit_model, expected_status_names):
        return None
    seen = []
    for name, statuses in board_column_mapping(edit_model):
        seen.append(f"{name}: {', '.join(statuses) if statuses else '—'}")
    desired = " | ".join(f"{name}: {name}" for name in expected_status_names)
    return "column/status mismatch; current=[" + " | ".join(seen) + f"]; expected=[{desired}]"


def is_tms_board(board: dict[str, Any], edit_model: dict[str, Any] | None, project_key: str) -> bool:
    if str(board.get("name", "")) in {f.panel_label_ru for f in FACETS}:
        return True
    if edit_model is None:
        return False
    filter_config = edit_model.get("filterConfig", {})
    if not isinstance(filter_config, dict):
        return False
    name = str(filter_config.get("name", ""))
    query = str(filter_config.get("query", ""))
    if name.startswith(f"{project_key} TMS board [") or name.startswith(f"{project_key} TMS panel ["):
        return True
    return f"project = {project_key}" in query and any(f'issuetype = "{f.issue_type}"' in query for f in FACETS)


def reset_project_panels(client: JiraClient, project_key: str) -> dict[str, Any]:
    deleted_boards: list[int] = []
    deleted_filters: list[int] = []
    filter_ids: set[int] = set()

    for board in client.get_boards(project_key):
        board_id = board.get("id")
        if board_id in (None, ""):
            continue
        bid = int(board_id)
        edit_model = client.get_board_edit_model(bid)
        if not is_tms_board(board, edit_model, project_key):
            continue
        filter_config = edit_model.get("filterConfig", {}) if edit_model else {}
        if isinstance(filter_config, dict) and filter_config.get("id") not in (None, ""):
            filter_ids.add(int(filter_config["id"]))
        if client.delete_board(bid):
            deleted_boards.append(bid)

    for filter_id in sorted(filter_ids):
        if client.delete_filter(filter_id):
            deleted_filters.append(filter_id)

    return {"boards": deleted_boards, "filters": deleted_filters}


def write_panels_doc(
    path: Path,
    *,
    project_key: str,
    base_url: str,
    items: dict[str, Any],
) -> None:
    lines = [
        f"# TMS / панели в проекте **{project_key}**",
        "",
        "Первые **три колонки** таблицы совпадают с эталоном в **`docs/tms.boards.md`** (та же доска по смыслу: название, тип issue, JQL).",
        "",
        "- **Панель проекта** — Issue Navigator внутри проекта: `/projects/{KEY}/issues?filter=…`.",
        "- **Rapid Board** — Kanban URL: `/secure/RapidBoard.jspa?rapidView=<id>` (пример: `http://host:8083/secure/RapidBoard.jspa?rapidView=9&selectedIssue=PROJ-80`). Параметр **`rapidView`** = числовой id Agile-доски (тот же, что `board_id` в REST и в `*.state.json` после **`--with-boards`**). Опционально **`selectedIssue`** открывает карточку.",
        "- Важно: Rapid Board корректна только когда **Board settings → Columns** настроены под статусы **этого** `issue type`. Скрипт **не создаёт и не меняет** статусы/workflow в Jira. Снимок того, что вернул `GET …/project/{KEY}/statuses`, попадает в state как `status_columns`; опционально можно включить **`--configure-board-columns`**, чтобы выставить колонки автоматически — по умолчанию вы делаете mapping в UI.",
        "",
        "**Фильтры** созданы через REST (`sharePermissions: project`) — доступ у тех же пользователей, кому доступен сам проект.",
        "",
        "| Доска (название) | Тип issue (Jira) | JQL | Панель проекта (`/projects/…/issues?filter=`) | Rapid Board (`rapidView`) |",
        "|------------------|------------------|-----|-----------------------------------------------|---------------------------|",
    ]
    for f in FACETS:
        row = merge_item(items, f.slug)
        fid = row.get("filter_id")
        if fid is None:
            continue
        fid_i = int(fid)
        jql = facet_jql(project_key, f.issue_type)
        purl = panel_issues_url(base_url, project_key, fid_i)
        bid = row.get("board_id")
        bid_i: int | None = int(bid) if bid not in (None, "") else None
        if bid_i is not None:
            rurl = rapid_board_url(base_url, bid_i)
            warning = row.get("board_column_warning")
            rapid_cell = f"`{rurl}`" + (" ⚠ column/status mismatch" if warning else "")
        else:
            rapid_cell = "—"
        lines.append(
            f"| {f.panel_label_ru} | `{f.issue_type}` | `{jql}` | `{purl}` | {rapid_cell} |"
        )
    lines.extend(
        [
            "",
            "Если колонка **Rapid Board** пустая (`—`): один раз выполните скрипт с **`--with-boards`** (или создайте доску вручную из того же сохранённого фильтра и пропишите `board_id` в state — id виден в URL доски или через `GET /rest/agile/1.0/board`).",
            "",
            "Если рядом с Rapid Board стоит **⚠ column/status mismatch**, настройте доску: **Board settings → Columns**. Целевой mapping: статусы из Jira для соответствующего `issue type`, по одному статусу в колонке.",
            "",
            "## Вручную: ярлык в сайдбаре проекта",
            "",
            "*Project settings → Project shortcuts* (или аналог в вашей версии Jira): добавьте ссылки (**проектную** или **Rapid**, по вкусу команды).",
            "",
            "Официального REST для системных shortcuts в DC часто нет — UI один раз после создания фильтров.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-key", required=True, help="Jira project key, e.g. KNX")
    ap.add_argument(
        "--base-url",
        default=os.environ.get("JIRA_URL", "").strip(),
        help="Jira base URL (default: env JIRA_URL)",
    )
    ap.add_argument(
        "--token",
        default=os.environ.get("JIRA_PERSONAL_TOKEN", "").strip(),
        help="PAT token (default: env JIRA_PERSONAL_TOKEN)",
    )
    ap.add_argument(
        "--state-file",
        type=Path,
        default=Path("docs/tms.panels.state.json"),
        help="Persist filter/board ids (default docs/tms.panels.state.json).",
    )
    ap.add_argument(
        "--write-panels-doc",
        type=Path,
        default=Path("docs/tms.panels.md"),
        help="Write project panel link table here (omit --no-write-panels-doc via default).",
    )
    ap.add_argument(
        "--no-write-panels-doc",
        action="store_true",
        help="Do not write docs/tms.panels.md.",
    )
    ap.add_argument(
        "--with-boards",
        action="store_true",
        help="Also create Jira Agile Kanban boards from each filter (legacy; can switch global context).",
    )
    ap.add_argument(
        "--reset-project-panels",
        action="store_true",
        help="Delete existing TMS boards/filters for the project before creating fresh ones. Implies --with-boards.",
    )
    ap.add_argument(
        "--configure-board-columns",
        action="store_true",
        help=(
            "After each Kanban board is created, PUT GreenHopper column mapping 1:1 from "
            "GET /project/{KEY}/statuses for that issue type. Off by default so you can "
            "fix workflows/statuses in Jira first, then map columns in the UI (or pass this flag once ready)."
        ),
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions only; no POST requests.",
    )
    ap.add_argument(
        "--insecure-tls",
        action="store_true",
        help="Skip TLS verification (only if HTTPS with broken cert).",
    )
    ns = ap.parse_args()

    if not ns.base_url or not ns.token:
        print("Set JIRA_URL and JIRA_PERSONAL_TOKEN (or pass --base-url/--token).", file=sys.stderr)
        return 2

    project_key = ns.project_key.strip().upper()
    state_path = ns.state_file
    blob = load_state(state_path)

    items: dict[str, Any] = dict(blob["items"])

    if ns.reset_project_panels:
        ns.with_boards = True

    print(
        f"project={project_key} base_url={ns.base_url} with_boards={ns.with_boards} "
        f"reset={ns.reset_project_panels} configure_board_columns={ns.configure_board_columns}"
    )
    if ns.dry_run:
        for f in FACETS:
            print(f"[dry-run] facet={f.slug} panel={f.panel_label_ru}")
            print(f"  filter_name={filter_name(project_key, f.slug)}")
            print(f"  jql={facet_jql(project_key, f.issue_type)}")
            print(f"  panel_url_template=.../projects/{project_key}/issues?filter=<filter_id>")
            print("  rapid_board_template=.../secure/RapidBoard.jspa?rapidView=<board_id>&selectedIssue=<KEY>")
        return 0

    client = JiraClient(ns.base_url, ns.token, ns.insecure_tls)
    proj = client.get_project(project_key)
    project_nid = str(proj["id"])
    statuses_by_issue_type = client.get_project_statuses(project_key)
    facet_status_tuples = [
        tuple(status_names(statuses_by_issue_type.get(f.issue_type, []))) for f in FACETS
    ]
    if len(set(facet_status_tuples)) == 1 and facet_status_tuples and facet_status_tuples[0]:
        print(
            "NOTE: Jira returns the same status list for every configured issue type "
            "(shared workflow/scheme until you differentiate them in Project settings)."
        )

    if ns.reset_project_panels:
        deleted = reset_project_panels(client, project_key)
        print(f"deleted boards={deleted['boards']} filters={deleted['filters']}")
        items = {}
        save_state(state_path, project_key=project_key, base_url=ns.base_url, items=items)

    summary: list[str] = []
    try:
        for f in FACETS:
            expected_statuses = statuses_by_issue_type.get(f.issue_type)
            if not expected_statuses:
                available = ", ".join(sorted(statuses_by_issue_type))
                raise RuntimeError(f"No Jira statuses found for issue type {f.issue_type!r}. Available: {available}")
            expected_status_names = status_names(expected_statuses)
            entry = merge_item(items, f.slug)
            fname = filter_name(project_key, f.slug)
            jql = facet_jql(project_key, f.issue_type)

            filter_id = entry.get("filter_id")
            fid: int | None = int(filter_id) if filter_id not in (None, "") else None
            if fid is not None and client.get_filter(fid) is None:
                fid = None

            if fid is None:
                filt = client.create_filter(fname, jql, project_nid)
                fid = int(filt["id"])
                entry["filter_id"] = fid
                entry["filter_name"] = fname
                print(f"created filter id={fid} name={fname}")
            else:
                print(f"reuse filter id={fid} name={entry.get('filter_name')}")

            purl = panel_issues_url(client.base, project_key, fid)
            entry["panel_url"] = purl
            print(f"  panel: {purl}")

            if ns.with_boards:
                board_id = entry.get("board_id")
                bid: int | None = int(board_id) if board_id not in (None, "") else None
                if bid is not None and client.get_board(bid) is None:
                    bid = None

                if bid is None:
                    brd = client.create_board(f.panel_label_ru, fid)
                    bid = int(brd["id"])
                    entry["board_id"] = bid
                    entry["board_self"] = brd.get("self")
                    print(f"  created agile board id={bid} title={f.panel_label_ru!r}")
                else:
                    existing = client.get_board(bid)
                    if existing:
                        entry.setdefault("board_self", existing.get("self"))
                    print(f"  reuse agile board id={bid}")
                if ns.configure_board_columns:
                    client.configure_board_columns(bid, expected_statuses)
                    print(
                        "  configured board columns from Jira issue statuses: "
                        + ", ".join(expected_status_names)
                    )
                else:
                    print(
                        "  skipped board column auto-config (fix workflows/statuses in Jira; "
                        "Board settings → Columns — or rerun with --configure-board-columns)."
                    )
                summary.append(f"{f.slug}: board_id={bid} (agile)")
            bf = entry.get("board_id")
            if bf not in (None, ""):
                try:
                    rbid = int(bf)
                    if client.get_board(rbid) is not None:
                        rbu = rapid_board_url(client.base, rbid)
                        entry["rapid_board_url"] = rbu
                        print(f"  rapid: {rbu}")
                        edit_model = client.get_board_edit_model(rbid)
                        if edit_model is not None and ns.configure_board_columns:
                            warning = board_column_warning(edit_model, expected_status_names)
                            if warning:
                                entry["board_column_warning"] = warning
                                print(f"  WARNING: {warning}")
                            else:
                                entry.pop("board_column_warning", None)
                                print("  board columns match issue statuses")
                        elif edit_model is not None:
                            entry.pop("board_column_warning", None)
                except ValueError:
                    pass

            entry.setdefault("issue_type", f.issue_type)
            entry.setdefault("jql", jql)
            entry["status_columns"] = expected_status_names
            items[f.slug] = entry
            save_state(state_path, project_key=project_key, base_url=ns.base_url, items=items)

            summary.append(f"{f.slug}: filter_id={fid} panel_url={purl}")

    finally:
        save_state(state_path, project_key=project_key, base_url=ns.base_url, items=items)

    if not ns.no_write_panels_doc and ns.write_panels_doc:
        write_panels_doc(ns.write_panels_doc, project_key=project_key, base_url=ns.base_url, items=items)
        print(f"wrote panels doc -> {ns.write_panels_doc}")

    print("---")
    for line in summary:
        print(line)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
