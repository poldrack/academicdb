"""Structural tests for the GitHub Actions pipeline workflows."""

import re
import shlex
from pathlib import Path

import pytest
import yaml

from academic.management.commands.pipeline_alert import Command

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
NAMES = ["weekly-sync", "publish", "heartbeat"]


def load(name):
    return yaml.safe_load((WORKFLOWS / f"{name}.yml").read_text())


def triggers(wf):
    # PyYAML parses the bare key `on` as boolean True.
    return wf.get("on", wf.get(True))


def steps(wf):
    return [s for job in wf["jobs"].values() for s in job["steps"]]


def run_commands(wf):
    return [s.get("run", "") for s in steps(wf)]


@pytest.fixture(params=NAMES)
def any_workflow_text(request):
    return (WORKFLOWS / f"{request.param}.yml").read_text()


def test_weekly_sync_schedule_and_dispatch():
    on = triggers(load("weekly-sync"))
    assert on["schedule"] == [{"cron": "0 13 * * 1"}]
    assert "workflow_dispatch" in on


def test_heartbeat_schedule():
    on = triggers(load("heartbeat"))
    assert on["schedule"] == [{"cron": "0 14 * * *"}]


def test_publish_triggers():
    on = triggers(load("publish"))
    assert on["repository_dispatch"]["types"] == ["review-pr-closed"]
    assert on["workflow_dispatch"]["inputs"]["pr"]["required"] is True


@pytest.mark.parametrize("name", ["weekly-sync", "publish"])
def test_pipeline_workflows_share_concurrency_group(name):
    conc = load(name)["concurrency"]
    assert conc["group"] == "academicdb-pipeline"
    assert conc["cancel-in-progress"] is False


def test_weekly_sync_step_order():
    wf = load("weekly-sync")
    runs = run_commands(wf)
    needles = ["backup_database --output-dir backups --upload", "weekly_sync", "publish_sites",
               "gh workflow enable"]
    idx = [next(i for i, r in enumerate(runs) if n in r) for n in needles]
    assert idx == sorted(idx) and len(set(idx)) == 4
    by_if = {s.get("if"): s.get("run", "") for s in steps(wf) if s.get("if")}
    assert "pipeline_alert failure" in by_if["failure()"]
    assert "pipeline_alert recovered" in by_if["success()"]


def test_every_secret_documented(any_workflow_text):
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Automation", 1)[1]
    section = re.split(r"\n## ", section, maxsplit=1)[0]
    for secret in re.findall(r"secrets\.([A-Z0-9_]+)", any_workflow_text):
        assert secret in section
    assert not re.search(r"echo[^\n]*secrets\.", any_workflow_text)


def test_app_tokens_per_owner():
    wf = load("publish")
    apps = [s for s in steps(wf)
            if s.get("uses") == "actions/create-github-app-token@v2"]
    assert len(apps) == 2
    by_owner = {s["with"]["owner"]: s for s in apps}
    assert by_owner["poldrack"]["with"]["repositories"] == "poldrack.github.io,academicdb"
    assert by_owner["poldracklab"]["with"]["repositories"] == "poldracklab.github.io"
    publish_env = {}
    for s in steps(wf):
        publish_env.update(s.get("env", {}))
    for owner, var in [("poldrack", "PERSONAL_GITHUB_TOKEN"),
                       ("poldracklab", "LAB_GITHUB_TOKEN")]:
        assert by_owner[owner]["id"] in publish_env[var]


@pytest.mark.parametrize("name", ["weekly-sync", "heartbeat"])
def test_keepalive_permissions(name):
    perms = load(name)["permissions"]
    assert perms["actions"] == "write"
    assert perms["issues"] == "write"
    assert perms["contents"] == "read"


def test_no_event_expressions_in_run_strings():
    for name in NAMES:
        for cmd in run_commands(load(name)):
            assert "${{ github.event." not in cmd


def test_publish_reads_pr_number_from_env():
    step = next(s for s in steps(load("publish"))
                if "process_review" in s.get("run", ""))
    assert "PR_NUMBER" in step["env"]
    assert "github.event.client_payload.pr" in step["env"]["PR_NUMBER"]
    assert '--pr "$PR_NUMBER"' in step["run"]
    assert "^[0-9]+$" in step["run"]


def test_heartbeat_keepalive_always_runs():
    step = next(s for s in steps(load("heartbeat"))
                if "gh workflow enable" in s.get("run", ""))
    assert step["if"] == "always()"


# pipeline_alert invocations must parse against the real command

RUN_URL_EXPR = ("${{ github.server_url }}/${{ github.repository }}"
                "/actions/runs/${{ github.run_id }}")


def _placeholders(text):
    text = re.sub(r"\$\{\{[^}]*\}\}", "EXPR", text)
    return re.sub(r"\$\{?([A-Z_][A-Z0-9_]*)\}?", r"VAR_\1", text)


def alert_steps():
    for name in NAMES:
        for step in steps(load(name)):
            if "pipeline_alert" in step.get("run", ""):
                yield name, step


def alert_argv(step):
    words = shlex.split(_placeholders(step["run"]))
    return words[words.index("pipeline_alert") + 1:]


def parse_alert(argv):
    parser = Command().create_parser("manage.py", "pipeline_alert")
    return parser.parse_args(argv)


def test_every_pipeline_alert_invocation_parses():
    found = list(alert_steps())
    for name, step in found:
        args = parse_alert(alert_argv(step))
        if args.action in ("failure", "recovered"):
            assert args.workflow == f"{name}.yml"
            assert args.run_url == "VAR_RUN_URL", (name, step["name"])
            assert step["env"]["RUN_URL"] == RUN_URL_EXPR
    assert len(found) == 5  # failure+recovered in two workflows, heartbeat


def test_publish_closes_alert_on_recovery():
    by_if = {s.get("if"): s.get("run", "") for s in steps(load("publish"))
             if s.get("if")}
    assert "pipeline_alert recovered" in by_if["success()"]
    assert "--workflow publish.yml" in by_if["success()"]


def test_heartbeat_can_be_dispatched():
    assert "workflow_dispatch" in triggers(load("heartbeat"))
