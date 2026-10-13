from pathlib import Path


WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "rag-quality-gate.yml"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_ragas_quality_gate_is_manual_only() -> None:
    text = _workflow_text()
    trigger_block = text.split("on:", 1)[1].split("jobs:", 1)[0]

    assert "workflow_dispatch:" in trigger_block
    assert "workflow_call:" not in trigger_block
    assert "schedule:" not in trigger_block
    assert "push:" not in trigger_block


def test_missing_ragas_configuration_skips_without_failing() -> None:
    text = _workflow_text()

    assert 'echo "configured=false" >> "$GITHUB_OUTPUT"' in text
    assert "::notice::RAGAS quality gate skipped" in text
    assert "exit 1" not in text
    assert "if: needs.configuration.outputs.configured == 'true'" in text


def test_configuration_job_can_read_staging_environment_secrets() -> None:
    text = _workflow_text()
    configuration_job = text.split("  configuration:", 1)[1].split("\n  ragas:", 1)[0]

    assert "    environment: staging" in configuration_job
