"""GitHub Actions contracts for optional feature environment wiring."""

from typing import Final

import pytest

from .workflow_config_support import load_workflow, run_environment


_WORKFLOW_NAMES: Final = ("main.yml", "test.yml")
_SECRET_NAMES: Final = (
    "NIH_API",
    "IEEE_XPLORE_API",
    "ELSEVIER_API",
    "SPRINGER_API",
)
_FALSE_VARIABLE_NAMES: Final = (
    "ABSTRACT_ENRICHMENT_ENABLED",
    "PUBMED_ENABLED",
    "IEEE_ENABLED",
    "ELSEVIER_ENABLED",
    "SPRINGER_ENABLED",
    "VENUE_PRESTIGE_ENABLED",
    "OPENALEX_ALLOW_ANONYMOUS",
    "SENT_DOI_STATE_ENABLED",
)


@pytest.mark.parametrize("workflow_name", _WORKFLOW_NAMES)
def test_provider_credentials_are_exported_only_from_secrets(
    workflow_name: str,
) -> None:
    # Given a checked-in runnable workflow.
    environment = run_environment(workflow_name)

    # When optional provider credential bindings are inspected.
    bindings = {name: environment.get(name) for name in _SECRET_NAMES}

    # Then every credential comes directly from its matching GitHub Secret.
    assert bindings == {
        name: f"${{{{ secrets.{name} }}}}" for name in _SECRET_NAMES
    }


@pytest.mark.parametrize("workflow_name", _WORKFLOW_NAMES)
def test_nonsecret_controls_are_exported_from_variables_with_safe_defaults(
    workflow_name: str,
) -> None:
    # Given a checked-in runnable workflow.
    environment = run_environment(workflow_name)

    # When nonsecret feature controls are inspected.
    bindings = {
        "CROSSREF_MAILTO": environment.get("CROSSREF_MAILTO"),
        "PUBMED_EMAIL": environment.get("PUBMED_EMAIL"),
        "PUBMED_QUERY": environment.get("PUBMED_QUERY"),
        "PUBMED_ISSNS": environment.get("PUBMED_ISSNS"),
        "PAPER_SOURCES": environment.get("PAPER_SOURCES"),
        **{name: environment.get(name) for name in _FALSE_VARIABLE_NAMES},
    }

    # Then values use repository Variables and every opt-in defaults to false.
    assert bindings == {
        "CROSSREF_MAILTO": "${{ vars.CROSSREF_MAILTO }}",
        "PUBMED_EMAIL": "${{ vars.PUBMED_EMAIL }}",
        "PUBMED_QUERY": "${{ vars.PUBMED_QUERY }}",
        "PUBMED_ISSNS": "${{ vars.PUBMED_ISSNS || '[]' }}",
        "PAPER_SOURCES": "${{ vars.PAPER_SOURCES || '[\"arxiv\",\"openalex\"]' }}",
        **{
            name: f"${{{{ vars.{name} || 'false' }}}}"
            for name in _FALSE_VARIABLE_NAMES
        },
    }


def test_main_workflow_is_dispatch_only() -> None:
    # Given the production workflow trigger map.
    trigger = load_workflow("main.yml")["on"]
    assert isinstance(trigger, dict)

    # When its triggers are inspected, then the delayed daily schedule is gone.
    assert "workflow_dispatch" in trigger
    assert "schedule" not in trigger


def test_digest_scheduler_wakes_every_thirty_minutes_and_dispatches_the_digest() -> None:
    # Given the scheduler workflow.
    workflow = load_workflow("digest-scheduler.yml")
    trigger = workflow["on"]
    assert isinstance(trigger, dict)

    # When its trigger and dispatch contract are inspected.
    assert trigger["schedule"] == [{"cron": "*/30 * * * *"}]
    permissions = workflow["permissions"]
    assert permissions == {"actions": "write", "contents": "read"}

    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    job = jobs["dispatch"]
    assert isinstance(job, dict)
    steps = job["steps"]
    assert isinstance(steps, list)
    gate, dispatch = steps
    script = gate["with"]["script"]
    assert isinstance(script, str)
    assert "Asia/Shanghai" in script
    assert "8 * 60 + 40" in script
    assert "9 * 60 + 40" in script
    assert "sent-doi-state-v1" in script

    # Then only the due step dispatches the real digest.
    assert dispatch["if"] == "steps.gate.outputs.due == 'true'"
    command = dispatch["run"]
    assert isinstance(command, str)
    assert "gh workflow run main.yml" in command
    assert '-f preview="$PREVIEW"' in command
    assert "-f refresh_digest=false" in command


def test_test_workflow_remains_manual_only() -> None:
    # Given the test workflow trigger map.
    trigger = load_workflow("test.yml")["on"]
    assert isinstance(trigger, dict)

    # When its triggers are inspected, then no scheduled execution exists.
    assert set(trigger) == {"workflow_dispatch"}
