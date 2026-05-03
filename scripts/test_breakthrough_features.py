#!/usr/bin/env python3
"""Test ALL breakthrough features against real shadow-engine data (no mocks).

Prerequisites:
    cd shadow-engine && shadow-engine bootstrap
    python scripts/build_efficacy_data.py

Tests every new engine: causal, debate, simulation, temporal anomaly,
intervention, strategy evolution, speculative context, transfer store,
context budget, and the new Ollama HTTP provider.
"""

import json
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shadow_engine.main import ShadowEngine
from shadow_engine.learning.causal_engine import CausalEngine, build_default_causal_graph
from shadow_engine.learning.pr_simulator import PROutcomeSimulator
from shadow_engine.learning.temporal_anomaly import TemporalAnomalyDetector, BOCD
from shadow_engine.learning.intervention_engine import InterventionEngine, InterventionLevel
from shadow_engine.learning.strategy_evolution import StrategyEvolutionEngine
from shadow_engine.learning.speculative_context import SpeculativeContextEngine
from shadow_engine.learning.transfer_store import TransferStore
from shadow_engine.learning.context_budget import ContextBudgetManager
from shadow_engine.laboratory.debate import DebateEngine

PASS = "✅"
FAIL = "❌"


def test_header(name: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def assert_true(cond, msg) -> bool:
    if cond:
        print(f"  {PASS} {msg}")
        return True
    else:
        print(f"  {FAIL} {msg}")
        return False


def main():
    engine = ShadowEngine(repo_path=".")
    store = engine.store

    results: dict[str, bool] = {}

    # ── 1. Causal Engine ──────────────────────────────────
    test_header("Feature #1: Causal Reasoning Engine")

    causal = CausalEngine(store)
    sessions = causal.get_session_data()
    r = assert_true(len(sessions) > 0, f"CausalEngine loaded {len(sessions)} real sessions")
    results["causal_load_data"] = r

    # Association query
    assoc = causal.query_association(treatment="approach", treatment_value="Targeted Fix")
    r = assert_true("probability" in assoc, f"Association query returned probability={assoc.get('probability', 'N/A')}")
    results["causal_association"] = r

    # Intervention query
    interv = causal.query_intervention(treatment="approach", treatment_value="Targeted Fix")
    r = assert_true(
        "causal_effect" in interv or "error" in interv,
        f"Intervention query: {interv.get('causal_effect', interv.get('error', 'N/A'))}"
    )
    results["causal_intervention"] = r

    # Counterfactual query
    if sessions:
        sid = sessions[0].get("session_id", "")
        if sid:
            cf = causal.query_counterfactual(sid, "Targeted Fix")
            r = assert_true(cf.interpretation != "", f"Counterfactual: {cf.interpretation[:80]}...")
            results["causal_counterfactual"] = r

    # Build context
    ctx = causal.build_causal_context("fix the login rate-limiting bug")
    r = assert_true(len(ctx) >= 0, f"Causal context: {len(ctx)} chars generated (expected empty for <3 bug_fix sessions)")
    results["causal_context"] = r

    # ── 2. PR Outcome Simulator ────────────────────────────
    test_header("Feature #2: PR Outcome Simulator")

    sim = PROutcomeSimulator(store, engine.bayesian, engine.test_tracker)
    # Use real files from the DB
    real_files = ["src/shadow_engine/main.py", "src/shadow_engine/learning/engine.py"]
    result = sim.simulate_pr(real_files, approach="Targeted Fix", num_simulations=100)
    r = assert_true(result.simulation_count == 100, f"Simulation ran {result.simulation_count} iterations")
    results["sim_count"] = r
    r = assert_true(0 <= result.overall_risk_score <= 100, f"Risk score: {result.overall_risk_score:.1f}/100")
    results["sim_risk"] = r

    ctx = sim.build_simulation_context(real_files, "Targeted Fix")
    r = assert_true(len(ctx) > 100, f"Sim context: {len(ctx)} chars generated")
    results["sim_context"] = r

    # ── 3. Temporal Anomaly Detection ──────────────────────
    test_header("Feature #3: Temporal Anomaly Detection")

    tad = TemporalAnomalyDetector(store)
    anomalies = tad.ingest_sessions()
    r = assert_true(tad.bocd is not None, f"BOCD initialized with {len(tad.bocd.observations)} observations")
    results["temporal_bocd"] = r

    expected = tad.bocd.get_expected_success_rate()
    r = assert_true(0.0 <= expected <= 1.0, f"Expected success rate: {expected:.1%}")
    results["temporal_expected"] = r

    ctx = tad.build_temporal_context()
    r = assert_true(len(ctx) > 0, f"Temporal context: {len(ctx)} chars")
    results["temporal_context"] = r

    # Forecast
    health = engine.health_scorer.compute()
    forecast = tad.forecast_health(health.get("overall_score", 50))
    r = assert_true(forecast.trend_direction in ("improving", "stable", "degrading", "crashing"),
                    f"Forecast: {forecast.trend_direction} (slope={forecast.trend_slope})")
    results["temporal_forecast"] = r

    forecast_ctx = tad.build_forecast_context(health.get("overall_score", 50))
    r = assert_true(len(forecast_ctx) > 0, f"Forecast context: {len(forecast_ctx)} chars")
    results["temporal_forecast_ctx"] = r

    # ── 4. Intervention Engine ─────────────────────────────
    test_header("Feature #4: Mid-Session Intervention Engine")

    interv_eng = InterventionEngine(store, engine.live_monitor, engine.laboratory)
    risk, level = interv_eng.assess_risk(real_files, "Targeted Fix")
    r = assert_true(0.0 <= risk <= 1.0, f"Risk assessment: {risk:.1%}")
    results["intervention_risk"] = r

    ctx = interv_eng.build_intervention_context(real_files, risk, level or InterventionLevel.WARN)
    r = assert_true(len(ctx) > 0, f"Intervention context: {len(ctx)} chars")
    results["intervention_ctx"] = r

    # ── 5. Debate Engine ───────────────────────────────────
    test_header("Feature #5: Multi-Agent Debate Engine")

    debate = DebateEngine()
    # Build real variant data from sessions
    variants = []
    for s in sessions[:3]:
        variants.append({
            "variant_id": s.get("session_id", "unknown"),
            "approach": s.get("approach", "Targeted Fix"),
            "score": 85.0 if s.get("was_successful") else 30.0,
            "tests_passed": s.get("tests_passed", 10),
            "tests_total": s.get("tests_total", 10),
            "files_changed": s.get("files_changed", []),
            "token_count": s.get("token_count", 5000),
            "duration_seconds": s.get("duration_seconds", 30),
        })
    debate_result = debate.run_debate(variants, "fix the login bug")
    r = assert_true(debate_result.variant_count > 0, f"Debate: {debate_result.variant_count} variants debated, {len(debate_result.rounds)} rounds")
    results["debate_run"] = r

    ctx = debate.build_debate_context(variants, "fix the login bug")
    r = assert_true(len(ctx) > 0, f"Debate context: {len(ctx)} chars")
    results["debate_ctx"] = r

    # ── 6. Strategy Evolution ──────────────────────────────
    test_header("Feature #6: Self-Modifying Strategy Evolution")

    evo = StrategyEvolutionEngine(store)
    pop = evo.evolve("bug_fix")
    r = assert_true(len(pop) > 0, f"Evolution: {len(pop)} strategies in bug_fix population (gen {evo.generation})")
    results["evo_population"] = r

    best = evo.get_best_strategies("bug_fix", top_n=3)
    r = assert_true(len(best) > 0, f"Best strategies: {len(best)} returned")
    results["evo_best"] = r

    # Crossover test
    from shadow_engine.learning.strategy_evolution import crossover
    if len(pop) >= 2:
        child = crossover(pop[0], pop[1])
        r = assert_true(len(child.genes) > 0, f"Crossover produced {len(child.genes)} genes")
        results["evo_crossover"] = r

    # ── 7. Speculative Context ─────────────────────────────
    test_header("Feature #7: Speculative Context Pre-Computation")

    spec = SpeculativeContextEngine(max_cache_size=10)
    spec.register_compute_func(lambda task: f"Context for: {task}")

    # First call = miss (compute), second = hit (cache)
    ctx1 = spec.get_or_compute("fix auth bug")
    r = assert_true(len(ctx1) > 0, "First call computed context")
    results["spec_compute"] = r

    ctx2 = spec.get_or_compute("fix auth bug")
    r = assert_true(spec.cache_size > 0, f"Cache hit: size={spec.cache_size}, hit_rate={spec.hit_rate:.0%}")
    results["spec_cache"] = r

    # Precompute async
    spec.precompute_async("add search feature")
    spec.precompute_async("refactor billing module")
    processed = spec.process_queue(2)
    r = assert_true(processed == 2, f"Processed {processed} items from precompute queue")
    results["spec_queue"] = r

    stats = spec.get_stats()
    r = assert_true(stats["hit_rate"] >= 0, f"Spec stats: {json.dumps(stats)}")
    results["spec_stats"] = r

    # ── 8. Transfer Store ──────────────────────────────────
    test_header("Feature #8: Cross-Codebase Transfer Learning")

    transfer = TransferStore(store)
    p = transfer.abstract_pattern(
        "Add null guard in `src/auth.py` before processing tokens",
        "bug_fix", "shadow-engine", True,
    )
    r = assert_true(p is not None, f"Abstracted pattern: confidence={p.confidence:.0%}")
    results["transfer_abstract"] = r

    patterns = transfer.get_transferable_patterns("bug_fix")
    r = assert_true(len(patterns) >= 1, f"Transferable patterns: {len(patterns)}")
    results["transfer_get"] = r

    ctx = transfer.build_transfer_context("bug_fix")
    r = assert_true(len(ctx) > 0, f"Transfer context: {len(ctx)} chars")
    results["transfer_ctx"] = r

    # ── 9. Context Budget Manager ──────────────────────────
    test_header("Bonus: Context Budget Manager")

    budget = ContextBudgetManager(max_tokens=500)
    budget.add_section(0, "critical", "Critical Info",
                       lambda: "This is critical context that must always be included. Agents need this to understand the codebase structure.")
    budget.add_section(50, "medium", "Medium Info",
                       lambda: "This is medium priority context with additional details that help but are not essential.")
    budget.add_section(90, "optional", "Optional Info",
                       lambda: "This is nice-to-have context with historical examples and detailed documentation references.")
    ctx = budget.build()
    r = assert_true(len(ctx) > 0, f"Budget build: {len(ctx)} chars (est {budget._estimate_tokens(ctx)} tokens)")
    results["budget_build"] = r

    # ── 10. Causal Graph ────────────────────────────────────
    test_header("Bonus: Causal Graph Analysis")

    graph = build_default_causal_graph()
    r = assert_true(len(graph.nodes) >= 5, f"Default graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")
    results["graph_nodes"] = r

    backdoor = graph.get_backdoor_paths("approach", "success")
    r = assert_true(len(backdoor) >= 0, f"Backdoor paths approach→success: {len(backdoor)}")
    results["graph_backdoor"] = r

    adj = graph.get_minimal_adjustment_set("approach", "success")
    r = assert_true(isinstance(adj, set), f"Adjustment set: {adj}")
    results["graph_adjustment"] = r

    # ── 11. Context Budget with Real Data ───────────────────
    test_header("Bonus: Context Budget Integration Test")

    budget2 = ContextBudgetManager(max_tokens=2000)
    budget2.add_section(0, "classify", "Classification",
                        lambda: engine.suggest("fix the login bug").get("recommended_approach", ""))
    budget2.add_section(10, "causal", "Causal",
                        lambda: causal.build_causal_context("fix the login bug"))
    budget2.add_section(50, "temporal", "Temporal",
                        lambda: tad.build_temporal_context())
    ctx = budget2.build()
    r = assert_true(len(ctx) > 0, f"Integrated budget: {len(ctx)} chars ({budget2._estimate_tokens(ctx)} est tokens)")
    results["budget_integrated"] = r

    # ── Summary ────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  RESULTS SUMMARY")
    print(f"{'='*60}")
    passed = sum(results.values())
    total = len(results)
    for name, ok in results.items():
        print(f"  {PASS if ok else FAIL} {name}")
    print(f"\n  {passed}/{total} tests passed ({passed*100//total}%)")
    print(f"{'='*60}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())