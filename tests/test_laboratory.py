"""Tests for Laboratory — experiment runner, variants, scoring."""

from shadow_engine.laboratory.experiment import (
    ExperimentRunner,
    ExperimentStatus,
    ExperimentVariant,
    ExperimentBatch,
    WinnerSelection,
)


class TestExperimentVariant:
    def test_variant_creation(self):
        v = ExperimentVariant(
            name="Test Variant",
            approach="Test approach description",
            model="claude-sonnet",
            prompt="Do something useful",
        )
        assert v.name == "Test Variant"
        assert v.status == ExperimentStatus.PENDING
        assert v.score == 0.0
        assert v.session_id is None
        assert len(v.variant_id) == 12

    def test_variant_to_session_record(self):
        v = ExperimentVariant(
            name="Test",
            approach="Approach",
            model="sonnet",
            prompt="Fix bug",
            status=ExperimentStatus.COMPLETED,
            session_id="sess-123",
            pr_url="https://github.com/pr/1",
            test_results={"total": 10, "passed": 10, "failed": 0},
            files_changed=["a.py", "b.py"],
            lines_added=15,
            lines_removed=3,
            duration_seconds=42.0,
            token_count=5000,
        )

        record = v.to_session_record("my-repo")
        assert record.session_id == "sess-123"
        assert record.repository == "my-repo"
        assert record.pr_url == "https://github.com/pr/1"

    def test_variant_ids_are_unique(self):
        v1 = ExperimentVariant(name="A")
        v2 = ExperimentVariant(name="B")
        assert v1.variant_id != v2.variant_id


class TestExperimentBatch:
    def test_batch_creation(self):
        v1 = ExperimentVariant(name="A")
        v2 = ExperimentVariant(name="B")
        batch = ExperimentBatch(
            repository="test-repo",
            task_description="Test task",
            variants=[v1, v2],
        )
        assert len(batch.variants) == 2
        assert batch.winner_variant_id is None
        assert batch.winning_variant is None

    def test_batch_to_summary(self):
        v1 = ExperimentVariant(name="A", approach="Approach A", model="sonnet",
                               status=ExperimentStatus.PENDING)
        v2 = ExperimentVariant(name="B", approach="Approach B", model="opus",
                               status=ExperimentStatus.COMPLETED, score=85.0,
                               test_results={"passed": 10, "failed": 0},
                               lines_added=5, lines_removed=2, duration_seconds=30.0,
                               token_count=4000)
        batch = ExperimentBatch(
            repository="test",
            task_description="Do thing",
            variants=[v1, v2],
        )

        summary = batch.to_summary()
        assert summary["total_variants"] == 2
        assert summary["completed"] == 1
        assert summary["pending"] == 1
        assert len(summary["variants"]) == 2


class TestExperimentRunner:
    def setup_method(self):
        self.runner = ExperimentRunner()

    def test_problem_classification_bug(self):
        pt = self.runner._classify_problem("fix the login bug in auth")
        assert pt == "bug_fix"

        pt = self.runner._classify_problem("the error handler is crashing")
        assert pt == "bug_fix"

    def test_problem_classification_feature(self):
        pt = self.runner._classify_problem("add a new search feature to the dashboard")
        assert pt == "feature"

        pt = self.runner._classify_problem("implement the create endpoint")
        assert pt == "feature"

    def test_problem_classification_refactor(self):
        pt = self.runner._classify_problem("refactor the billing module")
        assert pt == "refactor"

        pt = self.runner._classify_problem("clean up the old code and improve naming")
        assert pt == "refactor"

    def test_problem_classification_general(self):
        pt = self.runner._classify_problem("investigate something strange")
        assert pt == "general"

    def test_create_batch_with_default_strategies(self):
        batch = self.runner.create_batch(
            task_description="fix the authentication bug",
            repository="my-repo",
            num_variants=3,
        )
        assert len(batch.variants) == 3
        assert batch.problem_type == "bug_fix"
        # Bug fix strategies should be used
        names = {v.name for v in batch.variants}
        assert "Targeted Fix" in names
        assert "Root Cause + Guard" in names
        assert "Defense in Depth" in names

    def test_create_batch_with_custom_models(self):
        batch = self.runner.create_batch(
            task_description="add search feature",
            repository="my-repo",
            num_variants=2,
            models=["claude-sonnet", "claude-opus"],
        )
        assert len(batch.variants) == 2
        assert batch.variants[0].model == "claude-sonnet"
        assert batch.variants[1].model == "claude-opus"

    def test_create_batch_with_custom_strategies(self):
        batch = self.runner.create_batch(
            task_description="do something",
            repository="my-repo",
            num_variants=2,
            strategies=[
                {"name": "Custom A", "approach": "Do it fast"},
                {"name": "Custom B", "approach": "Do it well"},
            ],
        )
        assert batch.variants[0].name == "Custom A"
        assert batch.variants[1].name == "Custom B"

    def test_prompt_construction(self):
        prompt = self.runner._build_prompt("Fix the bug", "Be careful")
        assert "Fix the bug" in prompt
        assert "Be careful" in prompt
        assert "Understand the existing code" in prompt

    def test_scoring_perfect_variant(self):
        v = ExperimentVariant(
            name="Perfect",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 10, "passed": 10, "failed": 0},
            lines_added=5,
            lines_removed=1,
            files_changed=["a.py"],
            duration_seconds=10.0,
            token_count=1000,
        )
        batch = ExperimentBatch(variants=[v], winner_selection=WinnerSelection.BEST_PERFORMING)
        batch = self.runner.score_variants(batch)
        assert v.score > 80.0  # Should be very high
        assert batch.winner_variant_id == v.variant_id

    def test_scoring_failed_variant(self):
        v = ExperimentVariant(
            name="Failed",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 10, "passed": 2, "failed": 8},
            lines_added=200,
            lines_removed=150,
            files_changed=[f"f{i}.py" for i in range(15)],
            duration_seconds=300.0,
            token_count=50000,
        )
        batch = ExperimentBatch(variants=[v], winner_selection=WinnerSelection.BEST_PERFORMING)
        batch = self.runner.score_variants(batch)
        assert v.score < 40.0  # Should be low

    def test_scoring_picks_better_variant(self):
        v_good = ExperimentVariant(
            name="Good",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 10, "passed": 10, "failed": 0},
            lines_added=5,
            lines_removed=1,
            files_changed=["a.py"],
            duration_seconds=10.0,
            token_count=1000,
        )
        v_bad = ExperimentVariant(
            name="Bad",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 10, "passed": 3, "failed": 7},
            lines_added=100,
            lines_removed=80,
            files_changed=[f"f{i}.py" for i in range(12)],
            duration_seconds=200.0,
            token_count=30000,
        )
        batch = ExperimentBatch(
            variants=[v_good, v_bad],
            winner_selection=WinnerSelection.BEST_PERFORMING,
        )
        batch = self.runner.score_variants(batch)
        assert v_good.score > v_bad.score
        assert batch.winner_variant_id == v_good.variant_id

    def test_scoring_smallest_change_winner(self):
        v_large = ExperimentVariant(
            name="Large Change",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 10, "passed": 10},
            lines_added=50, lines_removed=40,
            files_changed=["a.py", "b.py"],
            duration_seconds=30, token_count=2000,
        )
        v_small = ExperimentVariant(
            name="Small Change",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 10, "passed": 10},
            lines_added=3, lines_removed=1,
            files_changed=["a.py"],
            duration_seconds=30, token_count=2000,
        )
        batch = ExperimentBatch(
            variants=[v_large, v_small],
            winner_selection=WinnerSelection.SMALLEST_CHANGE,
        )
        batch = self.runner.score_variants(batch)
        assert batch.winner_variant_id == v_small.variant_id

    def test_scoring_fastest_winner(self):
        v_slow = ExperimentVariant(
            name="Slow",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 5, "passed": 5},
            lines_added=10, lines_removed=2,
            files_changed=["a.py"],
            duration_seconds=120.0, token_count=5000,
        )
        v_fast = ExperimentVariant(
            name="Fast",
            status=ExperimentStatus.COMPLETED,
            test_results={"total": 5, "passed": 5},
            lines_added=10, lines_removed=2,
            files_changed=["a.py"],
            duration_seconds=15.0, token_count=5000,
        )
        batch = ExperimentBatch(
            variants=[v_slow, v_fast],
            winner_selection=WinnerSelection.FASTEST_EXECUTION,
        )
        batch = self.runner.score_variants(batch)
        assert batch.winner_variant_id == v_fast.variant_id

    def test_scoring_pending_variants_get_zero(self):
        v = ExperimentVariant(name="Pending", status=ExperimentStatus.PENDING)
        batch = ExperimentBatch(variants=[v])
        batch = self.runner.score_variants(batch)
        assert v.score == 0.0

    def test_comparison_report(self):
        v1 = ExperimentVariant(
            name="Winner", approach="Best approach",
            status=ExperimentStatus.COMPLETED, score=90.0,
            test_results={"total": 10, "passed": 10, "failed": 0},
            lines_added=5, lines_removed=1,
            files_changed=["a.py"], duration_seconds=20.0,
            token_count=3000, model="sonnet",
        )
        v2 = ExperimentVariant(
            name="Loser", approach="Bad approach",
            status=ExperimentStatus.COMPLETED, score=30.0,
            test_results={"total": 10, "passed": 3, "failed": 7},
            lines_added=100, lines_removed=80,
            files_changed=["a.py", "b.py"], duration_seconds=200.0,
            token_count=20000, model="opus",
        )
        batch = ExperimentBatch(
            repository="test",
            task_description="Test task",
            variants=[v1, v2],
            winner_variant_id=v1.variant_id,
        )

        report = self.runner.get_comparison_report(batch)
        assert "WINNER" in report
        assert "Winner" in report
        assert "Loser" in report
        assert "KEY INSIGHTS" in report