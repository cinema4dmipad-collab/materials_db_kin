#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "create_mr.py"
SPEC = importlib.util.spec_from_file_location("create_mr", SCRIPT_PATH)
assert SPEC is not None
create_mr = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(create_mr)


class TargetResolutionTests(unittest.TestCase):
    @staticmethod
    def fake_try_git(responses: dict[tuple[str, ...], str | None]):
        def _try_git(*args: str) -> str | None:
            return responses.get(args)

        return _try_git

    def test_cli_target_precedes_env_and_inference(self) -> None:
        with patch.dict(os.environ, {"MR_TARGET_BRANCH": "env-target"}), patch.object(
            create_mr,
            "resolve_parent_branch",
            side_effect=AssertionError("inference should not run"),
        ):
            self.assertEqual(
                create_mr.resolve_target_branch("cli-target", "feature"),
                "cli-target",
            )

    def test_env_target_precedes_inference(self) -> None:
        with patch.dict(os.environ, {"MR_TARGET_BRANCH": "env-target"}), patch.object(
            create_mr,
            "resolve_parent_branch",
            side_effect=AssertionError("inference should not run"),
        ):
            self.assertEqual(
                create_mr.resolve_target_branch(None, "feature"),
                "env-target",
            )

    def test_inferred_origin_branch_is_stripped_to_plain_target(self) -> None:
        responses = {
            ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): (
                "origin/main\norigin/feature"
            ),
            ("merge-base", "--is-ancestor", "HEAD", "origin/main"): None,
            ("merge-base", "HEAD", "origin/main"): "base-main",
            ("show", "-s", "--format=%ct", "base-main"): "100",
            ("rev-list", "--count", "base-main..HEAD"): "3",
        }

        with patch.object(
            create_mr, "try_git", side_effect=self.fake_try_git(responses)
        ):
            self.assertEqual(create_mr.resolve_parent_branch("feature"), "main")

    def test_descendant_remote_refs_are_excluded_from_inference(self) -> None:
        responses = {
            ("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"): (
                "origin/main\norigin/descendant\norigin/feature"
            ),
            ("merge-base", "--is-ancestor", "HEAD", "origin/main"): None,
            ("merge-base", "--is-ancestor", "HEAD", "origin/descendant"): "",
            ("merge-base", "HEAD", "origin/main"): "base-main",
            ("show", "-s", "--format=%ct", "base-main"): "100",
            ("rev-list", "--count", "base-main..HEAD"): "3",
        }

        with patch.object(
            create_mr, "try_git", side_effect=self.fake_try_git(responses)
        ):
            self.assertEqual(create_mr.resolve_parent_branch("feature"), "main")


if __name__ == "__main__":
    unittest.main()
