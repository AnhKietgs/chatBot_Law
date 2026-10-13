from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from golden import GoldenCase
from run_ragas import score_all_grounded_cases, score_grounded_case, score_metric


class FakeMetric:
    def __init__(self, value: float):
        self.value = value
        self.calls: list[dict] = []

    async def ascore(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(value=self.value)


def grounded_case() -> GoldenCase:
    return GoldenCase(
        id="tm-001",
        question="Mức phạt tối đa là bao nhiêu?",
        as_of_date="2026-10-12",
        expected_status="grounded",
        reference_answer="Không quá 8% giá trị phần nghĩa vụ bị vi phạm.",
        expected_citations=(),
        reviewed_by="Chuyên gia pháp lý",
        reviewed_at="2026-10-12",
        notes="",
    )


def test_scores_all_four_ragas_metrics_with_the_expected_inputs():
    metrics = {
        "faithfulness": FakeMetric(0.91),
        "answer_relevancy": FakeMetric(0.82),
        "context_precision": FakeMetric(0.83),
        "context_recall": FakeMetric(0.92),
    }
    trace = {
        "answer": {"answer": "Mức phạt không quá 8%."},
        "retrieved_contexts": ["Điều 301. Mức phạt không quá 8%..."],
    }

    scores = asyncio.run(score_grounded_case(metrics, grounded_case(), trace))

    assert scores == {
        "faithfulness": 0.91,
        "answer_relevancy": 0.82,
        "context_precision": 0.83,
        "context_recall": 0.92,
    }
    assert metrics["faithfulness"].calls[0]["retrieved_contexts"] == trace["retrieved_contexts"]
    assert metrics["context_precision"].calls[0]["reference"].startswith("Không quá 8%")
    assert metrics["context_recall"].calls[0]["reference"].startswith("Không quá 8%")


def test_scores_are_written_to_the_case_report():
    metrics = {name: FakeMetric(0.95) for name in (
        "faithfulness", "answer_relevancy", "context_precision", "context_recall",
    )}
    row = {"id": "tm-001", "metrics": {}}
    trace = {"answer": {"answer": "Không quá 8%."}, "retrieved_contexts": ["Điều 301..."]}

    asyncio.run(score_all_grounded_cases(metrics, [(grounded_case(), row, trace)]))

    assert row["metrics"] == {
        "faithfulness": 0.95,
        "answer_relevancy": 0.95,
        "context_precision": 0.95,
        "context_recall": 0.95,
    }
    assert "error" not in row


def test_metric_failure_is_recorded_and_never_silently_passes():
    class BrokenMetric(FakeMetric):
        async def ascore(self, **kwargs):
            raise RuntimeError("judge unavailable")

    metrics = {
        "faithfulness": BrokenMetric(0),
        "answer_relevancy": FakeMetric(1),
        "context_precision": FakeMetric(1),
        "context_recall": FakeMetric(1),
    }
    row = {"id": "tm-001", "metrics": {}}
    trace = {"answer": {"answer": "Không quá 8%."}, "retrieved_contexts": ["Điều 301..."]}

    asyncio.run(score_all_grounded_cases(metrics, [(grounded_case(), row, trace)]))

    assert row["metrics"] == {}
    assert row["error"] == "RAGAS scoring failed: RuntimeError: judge unavailable"


def test_score_metric_supports_reference_answer_compatibility_name():
    class CompatibilityMetric:
        async def ascore(self, **kwargs):
            if "reference" in kwargs:
                raise TypeError("unexpected keyword: reference")
            assert kwargs["reference_answer"] == "đáp án chuẩn"
            return 0.88

    value = asyncio.run(score_metric(CompatibilityMetric(), {"reference": "đáp án chuẩn"}))

    assert value == 0.88
