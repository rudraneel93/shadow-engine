"""Tests for experimental AI engines against real shadow-engine data.

These tests require a bootstrapped shadow-engine database with real session data.
Run: pip install -e ".[dev]" && shadow-engine bootstrap && pytest tests/test_experimental_engines.py
"""

import pytest
from shadow_engine.main import ShadowEngine
from shadow_engine.learning.causal_engine import CausalEngine, build_default_causal_graph
from shadow_engine.learning.pr_simulator import PROutcomeSimulator
from shadow_engine.learning.temporal_anomaly import TemporalAnomalyDetector
from shadow_engine.learning.intervention_engine import InterventionEngine, InterventionLevel
from shadow_engine.learning.strategy_evolution import StrategyEvolutionEngine, crossover
from shadow_engine.learning.speculative_context import SpeculativeContextEngine
from shadow_engine.learning.transfer_store import TransferStore
from shadow_engine.learning.context_budget import ContextBudgetManager
from shadow_engine.laboratory.debate import DebateEngine


@pytest.fixture(scope="module")
def engine():
    """Create a ShadowEngine connected to the real SQLite database."""
    return ShadowEngine(repo_path=".")


@pytest.fixture(scope="module")
def store(engine):
    return engine.store


@pytest.fixture(scope="module")
def causal(store):
    return CausalEngine(store)


@pytest.fixture(scope="module")
def sessions(causal):
    return causal.get_session_data()


class TestCausalEngine:
    def test_loads_real_sessions(self, sessions):
        assert len(sessions) > 0, "Should load real session data from SQLite"

    def test_query_association(self, causal):
        result = causal.query_association(treatment="approach", treatment_value="Targeted Fix")
        assert "probability" in result

    def test_query_intervention(self, causal):
        result = causal.query_intervention(treatment="approach", treatment_value="Targeted Fix")
        assert "causal_effect" in result or "error" in result

    def test_query_counterfactual(self, causal, sessions):
        if sessions:
            sid = sessions[0].get("session_id", "")
            if sid:
                cf = causal.query_counterfactual(sid, "Targeted Fix")
                assert cf.interpretation != ""

    def test_builds_causal_context(self, causal):
        ctx = causal.build_causal_context("fix the login rate-limiting bug")
        assert isinstance(ctx, str)


class TestCausalGraph:
    def test_default_graph(self):
        graph = build_default_causal_graph()
        assert len(graph.nodes) >= 5
        assert len(graph.edges) >= 10

    def test_backdoor_paths(self):
        graph = build_default_causal_graph()
        paths = graph.get_backdoor_paths("approach", "success")
        assert isinstance(paths, list)

    def test_adjustment_set(self):
        graph = build_default_causal_graph()
        adj = graph.get_minimal_adjustment_set("approach", "success")
        assert isinstance(adj, set)


class TestPROutcomeSimulator:
    def test_simulates_pr(self, store, engine):
        sim = PROutcomeSimulator(store, engine.bayesian, engine.test_tracker)
        result = sim.simulate_pr(
            ["src/shadow_engine/main.py", "src/shadow_engine/learning/engine.py"],
            approach="Targeted Fix",
            num_simulations=50,
        )
        assert result.simulation_count == 50
        assert 0 <= result.overall_risk_score <= 100

    def test_builds_simulation_context(self, store, engine):
        sim = PROutcomeSimulator(store, engine.bayesian, engine.test_tracker)
        ctx = sim.build_simulation_context(
            ["src/shadow_engine/main.py"], "Targeted Fix"
        )
        assert len(ctx) > 0


class TestTemporalAnomaly:
    def test_bocd_initialized(self, store):
        tad = TemporalAnomalyDetector(store)
        tad.ingest_sessions()
        assert len(tad.bocd.observations) > 0

    def test_expected_success_rate(self, store):
        tad = TemporalAnomalyDetector(store)
        tad.ingest_sessions()
        rate = tad.bocd.get_expected_success_rate()
        assert 0.0 <= rate <= 1.0

    def test_builds_temporal_context(self, store):
        tad = TemporalAnomalyDetector(store)
        ctx = tad.build_temporal_context()
        assert len(ctx) > 0

    def test_forecasts_health(self, store, engine):
        tad = TemporalAnomalyDetector(store)
        tad.ingest_sessions()
        health = engine.health_scorer.compute()
        forecast = tad.forecast_health(health.get("overall_score", 50))
        assert forecast.trend_direction in ("improving", "stable", "degrading", "crashing")


class TestInterventionEngine:
    def test_assesses_risk(self, store, engine):
        eng = InterventionEngine(store, engine.live_monitor)
        risk, level = eng.assess_risk(["src/shadow_engine/main.py"], "Targeted Fix")
        assert 0.0 <= risk <= 1.0

    def test_builds_context(self, store, engine):
        eng = InterventionEngine(store, engine.live_monitor)
        ctx = eng.build_intervention_context(
            ["src/shadow_engine/main.py"], 0.3, InterventionLevel.WARN
        )
        assert len(ctx) > 0


class TestDebateEngine:
    def test_runs_debate(self, sessions):
        if len(sessions) < 2:
            pytest.skip("Need at least 2 sessions for debate")
        debate = DebateEngine()
        variants = [
            {
                "variant_id": s.get("session_id", f"v{i}"),
                "approach": s.get("approach", "Targeted Fix"),
                "score": 85.0 if s.get("was_successful") else 30.0,
                "tests_passed": s.get("tests_passed", 10),
                "tests_total": s.get("tests_total", 10),
                "files_changed": s.get("files_changed", []),
                "token_count": s.get("token_count", 5000),
            }
            for i, s in enumerate(sessions[:3])
        ]
        result = debate.run_debate(variants, "fix the login bug")
        assert result.variant_count > 0

    def test_builds_debate_context(self, sessions):
        if len(sessions) < 2:
            pytest.skip("Need at least 2 sessions")
        debate = DebateEngine()
        variants = [{"variant_id": s.get("session_id", ""), "approach": s.get("approach", ""),
                      "score": 85.0, "tests_passed": 10, "tests_total": 10,
                      "files_changed": [], "token_count": 5000}
                     for s in sessions[:2]]
        ctx = debate.build_debate_context(variants, "fix bug")
        assert len(ctx) > 0


class TestStrategyEvolution:
    def test_evolves_population(self, store):
        evo = StrategyEvolutionEngine(store)
        pop = evo.evolve("bug_fix")
        assert len(pop) > 0

    def test_get_best_strategies(self, store):
        evo = StrategyEvolutionEngine(store)
        best = evo.get_best_strategies("bug_fix", top_n=3)
        assert len(best) > 0

    def test_crossover(self, store):
        evo = StrategyEvolutionEngine(store)
        pop = evo.evolve("bug_fix")
        if len(pop) >= 2:
            child = crossover(pop[0], pop[1])
            assert len(child.genes) > 0


class TestSpeculativeContext:
    def test_cache_hit_miss(self):
        spec = SpeculativeContextEngine(max_cache_size=10)
        spec.register_compute_func(lambda task: f"Context for: {task}")
        ctx1 = spec.get_or_compute("fix auth bug")
        assert len(ctx1) > 0
        ctx2 = spec.get_or_compute("fix auth bug")
        assert spec.cache_size > 0

    def test_precompute_queue(self):
        spec = SpeculativeContextEngine(max_cache_size=10)
        spec.register_compute_func(lambda task: f"Context: {task}")
        spec.precompute_async("task1")
        spec.precompute_async("task2")
        processed = spec.process_queue(2)
        assert processed == 2

    def test_stats(self):
        spec = SpeculativeContextEngine(max_cache_size=10)
        spec.register_compute_func(lambda task: f"Context: {task}")
        spec.get_or_compute("test")
        stats = spec.get_stats()
        assert "hit_rate" in stats


class TestTransferStore:
    def test_abstracts_pattern(self, store):
        transfer = TransferStore(store)
        p = transfer.abstract_pattern(
            "Add null guard in `src/auth.py` before processing tokens",
            "bug_fix", "shadow-engine", True,
        )
        assert p is not None

    def test_transferable_patterns(self, store):
        transfer = TransferStore(store)
        transfer.abstract_pattern("Test pattern", "bug_fix", "repo1", True)
        patterns = transfer.get_transferable_patterns("bug_fix")
        assert len(patterns) >= 1

    def test_builds_transfer_context(self, store):
        transfer = TransferStore(store)
        transfer.abstract_pattern("Test", "bug_fix", "repo1", True)
        ctx = transfer.build_transfer_context("bug_fix")
        assert len(ctx) > 0


class TestContextBudget:
    def test_builds_within_budget(self):
        budget = ContextBudgetManager(max_tokens=500)
        budget.add_section(0, "critical", "Critical", lambda: "This is critical. " * 10)
        budget.add_section(90, "optional", "Optional", lambda: "Optional extra. " * 20)
        ctx = budget.build()
        assert len(ctx) > 0

    def test_skips_low_priority_when_budget_exceeded(self):
        budget = ContextBudgetManager(max_tokens=100)
        budget.add_section(0, "critical", "Critical", lambda: "X" * 200)
        budget.add_section(90, "optional", "Optional", lambda: "Y" * 200)
        ctx = budget.build()
        assert "Y" not in ctx or "[...]" in ctx  # Optional section should be skipped or truncated

    def test_token_estimation(self):
        budget = ContextBudgetManager()
        tokens = budget._estimate_tokens("Hello world, this is a test.")
        assert tokens > 0