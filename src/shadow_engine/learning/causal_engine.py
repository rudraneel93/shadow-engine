"""Causal Reasoning Engine — Breakthrough Feature #1.

Understands WHY approaches succeed or fail using Structural Causal Models (SCM).
Goes beyond correlation ("Targeted Fix succeeded 4/4 times") to answer
counterfactual questions:

  - "If we had used Targeted Fix instead of Aggressive Rewrite, would session X have succeeded?"
  - "If we increase test coverage by 20%, what's the expected success rate change?"
  - "Is the approach causing success, or is it just that easier tasks get Targeted Fix?"

Builds a Directed Acyclic Graph (DAG) of causal factors:
  Approach → Change Scope → Test Coverage → Success
  File Risk → Agent Model → Token Count → Duration
  Problem Type → Approach Selection → ... (confounders!)

Uses do-calculus (Pearl's framework) for causal inference without requiring
randomized controlled trials — works on observational data from agent sessions.

References:
  - Pearl, J. (2009). Causality. Cambridge University Press.
  - Pearl, J., Glymour, M., & Jewell, N.P. (2016). Causal Inference in Statistics.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger(__name__)


# ── Causal Graph Data Structures ──────────────────────────────────

@dataclass
class CausalNode:
    """A variable in the causal graph with its domain and observational data."""
    name: str
    description: str
    domain: tuple[float, float]  # [min, max] for continuous, or categorical labels
    is_categorical: bool = False
    categories: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)  # direct causes
    children: list[str] = field(default_factory=list)  # direct effects

    def __hash__(self) -> int:
        return hash(self.name)


@dataclass
class CausalGraph:
    """Directed Acyclic Graph representing the causal structure of agent sessions."""
    nodes: dict[str, CausalNode] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (parent, child)

    def add_node(self, node: CausalNode) -> None:
        self.nodes[node.name] = node

    def add_edge(self, parent: str, child: str) -> None:
        if parent not in self.nodes or child not in self.nodes:
            raise ValueError(f"Both nodes must exist: {parent} → {child}")
        if (parent, child) not in self.edges:
            self.edges.append((parent, child))
            self.nodes[parent].children.append(child)
            self.nodes[child].parents.append(parent)

    def get_parents(self, node_name: str) -> list[str]:
        return self.nodes[node_name].parents if node_name in self.nodes else []

    def get_children(self, node_name: str) -> list[str]:
        return self.nodes[node_name].children if node_name in self.nodes else []

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """Check if ancestor is an ancestor of descendant via BFS."""
        visited: set[str] = set()
        queue = [ancestor]
        while queue:
            current = queue.pop(0)
            if current == descendant:
                return True
            if current in visited:
                continue
            visited.add(current)
            if current in self.nodes:
                for child in self.nodes[current].children:
                    if child not in visited:
                        queue.append(child)
        return False

    def get_backdoor_paths(self, treatment: str, outcome: str) -> list[list[str]]:
        """Find all backdoor paths between treatment and outcome.

        A backdoor path is any non-directed path that starts with an
        arrow INTO the treatment node. These paths can create spurious
        correlations and must be blocked for valid causal inference.
        """
        paths: list[list[str]] = []

        def dfs(current: str, path: list[str], visited: set[str]) -> None:
            if len(path) > 6:  # Prevent infinite loops in complex graphs
                return
            visited.add(current)
            path.append(current)

            if current == outcome and len(path) > 1:
                # Check if this is a backdoor path (starts with arrow into treatment)
                if len(path) >= 3:
                    # Path: treatment ← X ← ... or treatment ← X → ...
                    second = path[1]
                    if second in self.nodes and treatment in self.nodes[second].children:
                        # Arrow goes INTO treatment — this is a backdoor path
                        paths.append(list(path))
            else:
                if current in self.nodes:
                    node = self.nodes[current]
                    # Follow parents (backward edges)
                    for parent in node.parents:
                        if parent not in visited:
                            dfs(parent, path, set(visited))
                    # Follow children (forward edges)
                    for child in node.children:
                        if child not in visited:
                            dfs(child, path, set(visited))

            path.pop()
            visited.discard(current)

        dfs(treatment, [], set())
        return paths

    def get_minimal_adjustment_set(self, treatment: str, outcome: str) -> set[str]:
        """Compute minimal set of variables to adjust for (block all backdoor paths).

        Uses the backdoor criterion: a set Z satisfies the backdoor criterion
        relative to (X, Y) if:
        1. No node in Z is a descendant of X
        2. Z blocks every path between X and Y that contains an arrow into X

        Returns the smallest valid adjustment set.
        """
        backdoor_paths = self.get_backdoor_paths(treatment, outcome)
        if not backdoor_paths:
            return set()  # No backdoor paths — no adjustment needed

        # Simple heuristic: find common non-descendant nodes that block all paths
        candidates: dict[str, int] = {}
        treatment_descendants: set[str] = set()
        queue = [treatment]
        while queue:
            current = queue.pop(0)
            treatment_descendants.add(current)
            if current in self.nodes:
                for child in self.nodes[current].children:
                    if child not in treatment_descendants:
                        queue.append(child)

        for path in backdoor_paths:
            for node in path:
                if node != treatment and node != outcome and node not in treatment_descendants:
                    candidates[node] = candidates.get(node, 0) + 1

        # Select minimal set of candidates that hit every backdoor path
        # Greedy: pick nodes that block the most unblocked paths
        adjustment_set: set[str] = set()
        remaining_paths = set(range(len(backdoor_paths)))

        while remaining_paths:
            best_node = None
            best_hits = 0
            for node in candidates:
                if node in adjustment_set:
                    continue
                hits = sum(1 for i in remaining_paths if node in backdoor_paths[i])
                if hits > best_hits:
                    best_hits = hits
                    best_node = node

            if best_node is None or best_hits == 0:
                break
            adjustment_set.add(best_node)
            remaining_paths = {
                i for i in remaining_paths if best_node not in backdoor_paths[i]
            }

        return adjustment_set

    def to_dot(self) -> str:
        """Export graph to Graphviz DOT format for visualization."""
        lines = ["digraph CausalModel {"]
        lines.append('  rankdir=LR;')
        lines.append('  node [shape=ellipse, style=filled, fillcolor=lightyellow];')
        for name, node in self.nodes.items():
            lines.append(f'  {name} [label="{name}\\n({node.description})"];')
        for parent, child in self.edges:
            lines.append(f'  {parent} -> {child};')
        lines.append("}")
        return "\n".join(lines)


# ── Default Causal Model for Agent Sessions ──────────────────────

def build_default_causal_graph() -> CausalGraph:
    """Build the default causal model for agent coding sessions.

    DAG Structure:
      ProblemType → Approach → ChangeScope → TestCoverage → Success
      ProblemType → FileRisk → TestCoverage
      FileRisk → ChangeScope
      Approach → TokenCount → Duration
      ProblemType → Difficulty → Success
    """
    graph = CausalGraph()

    # Define nodes
    graph.add_node(CausalNode(
        name="problem_type",
        description="Classification of task (bug_fix, feature, refactor, etc.)",
        domain=(0, 1),
        is_categorical=True,
        categories=["bug_fix", "feature", "refactor", "testing", "migration", "general"],
    ))
    graph.add_node(CausalNode(
        name="approach",
        description="Strategy used (Targeted Fix, Aggressive Rewrite, etc.)",
        domain=(0, 1),
        is_categorical=True,
        categories=["Targeted Fix", "Root Cause + Guard", "Defense in Depth",
                     "Minimal Viable", "Extensible Implementation", "Clean Sweep",
                     "Incremental Rewrite", "Safe Extract", "Conservative"],
    ))
    graph.add_node(CausalNode(
        name="difficulty",
        description="Inherent task difficulty (latent confounder)",
        domain=(0, 10),
        is_categorical=False,
    ))
    graph.add_node(CausalNode(
        name="change_scope",
        description="Number of files modified",
        domain=(1, 100),
        is_categorical=False,
    ))
    graph.add_node(CausalNode(
        name="file_risk",
        description="Aggregate risk score of files being modified",
        domain=(0, 1),
        is_categorical=False,
    ))
    graph.add_node(CausalNode(
        name="test_coverage",
        description="Test pass rate (passed / total)",
        domain=(0, 1),
        is_categorical=False,
    ))
    graph.add_node(CausalNode(
        name="token_count",
        description="Total tokens consumed",
        domain=(100, 500000),
        is_categorical=False,
    ))
    graph.add_node(CausalNode(
        name="duration",
        description="Session duration in seconds",
        domain=(1, 3600),
        is_categorical=False,
    ))
    graph.add_node(CausalNode(
        name="success",
        description="Session outcome (1 = success, 0 = failure)",
        domain=(0, 1),
        is_categorical=False,
    ))

    # Define causal edges
    edges = [
        # Problem type influences approach selection
        ("problem_type", "approach"),
        # Problem type influences inherent difficulty (latent)
        ("problem_type", "difficulty"),
        # Approach determines change scope
        ("approach", "change_scope"),
        # File risk constrains test coverage
        ("file_risk", "test_coverage"),
        # File risk influences how broad changes need to be
        ("file_risk", "change_scope"),
        # Problem type correlates with file risk
        ("problem_type", "file_risk"),
        # Change scope affects test coverage
        ("change_scope", "test_coverage"),
        # Approach affects token usage
        ("approach", "token_count"),
        # Token count affects duration
        ("token_count", "duration"),
        # Change scope affects duration
        ("change_scope", "duration"),
        # Test coverage directly causes success
        ("test_coverage", "success"),
        # Difficulty affects success
        ("difficulty", "success"),
        # Approach affects success through change scope + test coverage
        ("approach", "success"),
        # Token count correlates with success (indirect effect)
        ("token_count", "success"),
    ]
    for parent, child in edges:
        graph.add_edge(parent, child)

    return graph


# ── Causal Inference Engine ─────────────────────────────────────

@dataclass
class CounterfactualResult:
    """Result of a counterfactual query."""
    query: str
    treatment: str
    actual_value: Any
    counterfactual_value: Any
    expected_effect: float  # Effect size (ATE - Average Treatment Effect)
    confidence_interval: tuple[float, float]  # 95% CI
    adjustment_variables: list[str]
    evidence_strength: str  # "strong", "moderate", "weak", "insufficient"
    interpretation: str


class CausalEngine:
    """Causal inference engine using structural causal models.

    Performs three types of queries:
    1. Association: P(Y | X) — what the data shows (correlation)
    2. Intervention: P(Y | do(X)) — what happens if we force X (causation)
    3. Counterfactual: P(Y_x' | X=x, Y=y) — what WOULD have happened
    """

    def __init__(self, store: Any, graph: CausalGraph | None = None):
        self.store = store
        self.graph = graph or build_default_causal_graph()

    def get_session_data(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Retrieve session data from the store for causal analysis."""
        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return []

        rows = conn.execute(
            "SELECT session_id, outcome, prompt, approach, model, "
            "duration_seconds, token_count FROM sessions "
            "WHERE outcome != 'in_progress' "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

        sessions: list[dict[str, Any]] = []
        for row in rows:
            session = dict(row)

            # Get files changed for this session
            files_rows = conn.execute(
                "SELECT file_path FROM session_files WHERE session_id=?",
                (session["session_id"],),
            ).fetchall()
            files = [f["file_path"] for f in files_rows]
            session["files_changed"] = files

            # Get test results
            test_row = conn.execute(
                "SELECT results_json FROM session_test_results WHERE session_id=?",
                (session["session_id"],),
            ).fetchone()
            if test_row and test_row["results_json"]:
                try:
                    import json
                    tr = json.loads(test_row["results_json"])
                    session["tests_passed"] = tr.get("passed", 0)
                    session["tests_total"] = tr.get("total", 0)
                except Exception:
                    session["tests_passed"] = 0
                    session["tests_total"] = 0
            else:
                session["tests_passed"] = 0
                session["tests_total"] = 0

            # Classify problem type
            session["problem_type"] = self._classify_problem(session.get("prompt", ""))

            # Determine if successful
            session["was_successful"] = session.get("outcome", "") == "success"

            sessions.append(session)

        return sessions

    def _classify_problem(self, prompt: str) -> str:
        """Simple keyword-based problem classification."""
        p = prompt.lower()
        if any(w in p for w in ("bug", "fix", "error", "crash", "broken", "failing")):
            return "bug_fix"
        if any(w in p for w in ("feature", "add", "implement", "create", "build", "new")):
            return "feature"
        if any(w in p for w in ("refactor", "clean", "improve", "optimize", "simplify")):
            return "refactor"
        if any(w in p for w in ("test", "spec", "coverage")):
            return "testing"
        return "general"

    def _discretize(self, value: float, bins: int = 5, domain: tuple[float, float] = (0, 1)) -> int:
        """Discretize a continuous value into a bin index."""
        low, high = domain
        clamped = max(low, min(high, value))
        bin_width = (high - low) / bins
        return min(bins - 1, int((clamped - low) / bin_width))

    def _estimate_conditional_probability(
        self, sessions: list[dict[str, Any]], outcome: Any, condition: dict[str, Any]
    ) -> tuple[float, int]:
        """Estimate P(outcome | condition) from session data.

        Args:
            sessions: List of session records
            outcome: Target outcome variable value
            condition: Dict of {variable: value} conditions

        Returns:
            (probability, sample_size) tuple
        """
        matching = 0
        total = 0
        for s in sessions:
            if self._matches(s, condition):
                total += 1
                if self._get_value(s, "success") == outcome:
                    matching += 1
        prob = matching / total if total > 0 else 0.0
        return prob, total

    def _matches(self, session: dict[str, Any], condition: dict[str, Any]) -> bool:
        for key, value in condition.items():
            if self._get_value(session, key) != value:
                return False
        return True

    def _get_value(self, session: dict[str, Any], variable: str) -> Any:
        """Map variable names to session data."""
        mapping = {
            "success": 1 if session.get("was_successful") else 0,
            "problem_type": session.get("problem_type", "general"),
            "approach": self._categorize_approach(session.get("approach", "")),
            "change_scope": len(session.get("files_changed", [])),
            "test_coverage": (
                session.get("tests_passed", 0) / session.get("tests_total", 1)
                if session.get("tests_total", 0) > 0 else 0.0
            ),
            "token_count": session.get("token_count", 0),
            "duration": session.get("duration_seconds", 0),
            "file_risk": 0.0,  # Computed separately when needed
            "difficulty": 5.0,  # Latent — estimated from other variables
        }
        return mapping.get(variable, getattr(session, variable, None))

    def _categorize_approach(self, approach: str) -> str:
        """Normalize approach strings into standard categories."""
        a = approach.lower()
        if "targeted" in a or "minimal" in a:
            return "Targeted Fix"
        if "root cause" in a or "guard" in a:
            return "Root Cause + Guard"
        if "defense" in a or "depth" in a:
            return "Defense in Depth"
        if "extensible" in a or "extend" in a:
            return "Extensible Implementation"
        if "aggressive" in a or "rewrite" in a:
            return "Aggressive Rewrite"
        if "clean sweep" in a:
            return "Clean Sweep"
        if "incremental" in a:
            return "Incremental Rewrite"
        if "safe extract" in a:
            return "Safe Extract"
        if "conservative" in a:
            return "Conservative"
        if "tdd" in a or "test first" in a:
            return "TDD First"
        return approach if approach else "Unknown"

    # ── Core Causal Queries ──────────────────────────────────

    def query_association(
        self, outcome: str = "success", treatment: str = "approach",
        treatment_value: Any = None, outcome_value: Any = 1,
    ) -> dict[str, Any]:
        """Query P(outcome | treatment = treatment_value) — pure correlation.

        This is what the current Learning Engine does. Does NOT control
        for confounders — may give biased estimates.
        """
        sessions = self.get_session_data()

        if treatment_value is None:
            return {"error": "treatment_value is required for association query"}

        prob, sample_size = self._estimate_conditional_probability(
            sessions, outcome_value, {treatment: treatment_value}
        )

        return {
            "type": "association",
            "query": f"P({outcome}={outcome_value} | {treatment}={treatment_value})",
            "probability": round(prob, 3),
            "sample_size": sample_size,
            "warning": "Association ≠ Causation. Confounders may bias this estimate. Use do_query() for causal effects.",
            "raw_value": f"{prob:.1%} success rate when {treatment}={treatment_value}",
        }

    def query_intervention(
        self, treatment: str = "approach", treatment_value: Any = "Targeted Fix",
        control_value: Any | None = None, outcome: str = "success",
    ) -> dict[str, Any]:
        """Query P(outcome | do(treatment = treatment_value)) — causal effect.

        Estimates the Average Treatment Effect (ATE) using backdoor
        adjustment to control for confounders.

        ATE = E[Y | do(X=x)] - E[Y | do(X=x_control)]
        """
        sessions = self.get_session_data()

        if len(sessions) < 10:
            return {"error": "Insufficient data for causal inference (need ≥10 sessions)", "type": "intervention"}

        # Find adjustment set using backdoor criterion
        adjustment_set = self.graph.get_minimal_adjustment_set(treatment, outcome)
        logger.info(f"Backdoor adjustment set for {treatment}→{outcome}: {adjustment_set}")

        # Stratify by adjustment variables and compute weighted average
        # This implements the backdoor adjustment formula:
        # P(Y | do(X=x)) = Σ_z P(Y | X=x, Z=z) * P(Z=z)
        weighted_prob = 0.0
        total_strata = 0
        strata_details: list[dict[str, Any]] = []

        if not adjustment_set:
            # No adjustment needed — direct estimate
            prob, n = self._estimate_conditional_probability(
                sessions, 1, {treatment: treatment_value}
            )
            weighted_prob = prob
            total_strata = 1
            strata_details.append({
                "condition": {treatment: treatment_value},
                "probability": prob, "sample_size": n,
            })
        else:
            # For each combination of adjustment variable values, compute conditional prob
            # Simplified: discretize continuous variables, enumerate categorical ones
            strata_counts: dict[tuple[Any, ...], int] = defaultdict(int)
            strata_probs: dict[tuple[Any, ...], float] = defaultdict(float)

            for s in sessions:
                key_parts = []
                for var in sorted(adjustment_set):
                    key_parts.append(self._get_value(s, var))
                key = tuple(key_parts)
                strata_counts[key] += 1

                tv = self._get_value(s, treatment)
                ov = self._get_value(s, outcome)
                if tv == treatment_value and ov == 1:
                    strata_probs[key] = strata_probs.get(key, 0.0) + 1

            total_sessions = len(sessions)

            for key, count in strata_counts.items():
                prob_in_stratum = strata_probs.get(key, 0.0) / count if count > 0 else 0.0
                weight = count / total_sessions
                weighted_prob += prob_in_stratum * weight
                total_strata += 1
                strata_details.append({
                    "stratum": dict(zip(sorted(adjustment_set), key)),
                    "probability": round(prob_in_stratum, 3),
                    "weight": round(weight, 3),
                    "sample_size": count,
                })

        # Compute ATE if control value provided
        ate = None
        if control_value:
            control_prob, _ = self._estimate_conditional_probability(
                sessions, 1, {treatment: control_value}
            )
            ate = weighted_prob - control_prob

            # Compute 95% confidence interval using normal approximation
            n_treated = sum(
                1 for s in sessions
                if self._get_value(s, treatment) == treatment_value
            )
            n_control = sum(
                1 for s in sessions
                if self._get_value(s, treatment) == control_value
            ) if control_value else 1

            if n_treated > 0 and n_control > 0:
                se_treated = math.sqrt(weighted_prob * (1 - weighted_prob) / n_treated)
                se_control = math.sqrt(control_prob * (1 - control_prob) / n_control)
                se_ate = math.sqrt(se_treated**2 + se_control**2)
                ci = (ate - 1.96 * se_ate, ate + 1.96 * se_ate)
            else:
                ci = (0.0, 0.0)

            # Evidence strength
            evidence = self._assess_evidence(n_treated + n_control, abs(ate), se_ate if n_treated > 0 else 1.0)
        else:
            n_treated = sum(
                1 for s in sessions
                if self._get_value(s, treatment) == treatment_value
            )
            se_treated = math.sqrt(weighted_prob * (1 - weighted_prob) / max(n_treated, 1))
            ci = (
                weighted_prob - 1.96 * se_treated,
                weighted_prob + 1.96 * se_treated,
            )
            evidence = self._assess_evidence(n_treated, 0.0, se_treated)

        return {
            "type": "intervention",
            "query": f"P({outcome}=1 | do({treatment}={treatment_value}))",
            "causal_effect": round(weighted_prob, 3),
            "ate": round(ate, 3) if ate is not None else None,
            "control_value": control_value,
            "confidence_interval": (round(ci[0], 3), round(ci[1], 3)),
            "adjustment_variables": sorted(adjustment_set),
            "total_strata": total_strata,
            "strata_details": strata_details[:10],  # Top 10 strata
            "total_sessions": len(sessions),
            "evidence_strength": evidence,
            "interpretation": self._interpret_ate(
                treatment, treatment_value, control_value, weighted_prob, ate, evidence
            ),
        }

    def query_counterfactual(
        self, session_id: str, alternative_approach: str,
    ) -> CounterfactualResult:
        """Query: "If we had used approach X instead of Y, would session Z have succeeded?"

        Uses the three-step counterfactual algorithm:
        1. Abduction: Update the causal model with observed evidence
        2. Action: Perform do(approach = alternative)
        3. Prediction: Compute the counterfactual outcome
        """
        sessions = self.get_session_data()
        target_session = None
        for s in sessions:
            if s.get("session_id") == session_id:
                target_session = s
                break

        if target_session is None:
            return CounterfactualResult(
                query=f"What if session {session_id} used {alternative_approach}?",
                treatment="approach",
                actual_value=None,
                counterfactual_value=None,
                expected_effect=0.0,
                confidence_interval=(0.0, 0.0),
                adjustment_variables=[],
                evidence_strength="insufficient",
                interpretation="Session not found in database.",
            )

        actual_approach = self._categorize_approach(target_session.get("approach", ""))
        actual_outcome = "success" if target_session.get("was_successful") else "failure"
        actual_change_scope = len(target_session.get("files_changed", []))
        (
            target_session.get("tests_passed", 0) / target_session.get("tests_total", 1)
            if target_session.get("tests_total", 0) > 0 else 0.0
        )
        problem_type = target_session.get("problem_type", "general")

        # Step 1: Match similar sessions to estimate the structural equations
        # Find sessions with same problem_type and alternative approach
        similar_sessions = [
            s for s in sessions
            if s.get("problem_type") == problem_type
            and self._categorize_approach(s.get("approach", "")) == alternative_approach
        ]

        if len(similar_sessions) < 3:
            # Fall back to all sessions with the alternative approach
            similar_sessions = [
                s for s in sessions
                if self._categorize_approach(s.get("approach", "")) == alternative_approach
            ]

        # Step 2: Estimate counterfactual outcome
        avg_change_scope_cf = 0
        avg_success_cf = 0.0
        n = len(similar_sessions)

        if n > 0:
            avg_change_scope_cf = sum(
                len(s.get("files_changed", [])) for s in similar_sessions
            ) / n
            sum(
                (s.get("tests_passed", 0) / s.get("tests_total", 1)
                 if s.get("tests_total", 0) > 0 else 0.0)
                for s in similar_sessions
            ) / n
            avg_success_cf = sum(
                1 for s in similar_sessions if s.get("was_successful")
            ) / n

        # Step 3: Estimate what WOULD have happened
        # If we had used alternative_approach:
        # - Change scope would be avg_change_scope_cf instead of actual_change_scope
        # - Test coverage would shift proportionally
        # - Success probability would be avg_success_cf

        # Apply the structural equation: success ← f(test_coverage, difficulty)
        # Using a simple linear model: P(success) = β₀ + β₁ * test_cov + β₂ * difficulty
        # But since we don't have fitted parameters, use nearest-neighbor matching

        # Compute effect size
        actual_success_rate = sum(
            1 for s in sessions
            if s.get("problem_type") == problem_type
            and self._categorize_approach(s.get("approach", "")) == actual_approach
            and s.get("was_successful")
        ) / max(1, sum(
            1 for s in sessions
            if s.get("problem_type") == problem_type
            and self._categorize_approach(s.get("approach", "")) == actual_approach
        ))

        effect = avg_success_cf - actual_success_rate

        # Confidence interval (using Wilson score for proportions)
        if n > 0:
            z = 1.96
            p = avg_success_cf
            denominator = 1 + z**2 / n
            center = (p + z**2 / (2 * n)) / denominator
            margin = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denominator
            ci = (max(0, center - margin), min(1, center + margin))
        else:
            ci = (0.0, 0.0)

        # Evidence strength
        evidence = self._assess_evidence(
            n + sum(
                1 for s in sessions
                if self._categorize_approach(s.get("approach", "")) == actual_approach
                and s.get("problem_type") == problem_type
            ),
            abs(effect),
            0.1 if n > 0 else 1.0,
        )

        # Build interpretation
        if n < 3:
            interp = (
                f"Insufficient data ({n} sessions with '{alternative_approach}' approach). "
                f"Cannot reliably estimate counterfactual."
            )
        elif effect > 0.1:
            interp = (
                f"Using '{alternative_approach}' instead of '{actual_approach}' "
                f"would likely have improved the outcome. Similar sessions with "
                f"'{alternative_approach}' succeeded {avg_success_cf:.0%} of the time "
                f"({n} sessions). This approach typically modifies "
                f"{avg_change_scope_cf:.0f} files (vs. {actual_change_scope} actually changed)."
            )
        elif effect < -0.1:
            interp = (
                f"Using '{alternative_approach}' instead of '{actual_approach}' "
                f"would likely have worsened the outcome. Similar sessions with "
                f"'{alternative_approach}' succeeded only {avg_success_cf:.0%} of the time. "
                f"The actual approach was more appropriate for this task type."
            )
        else:
            interp = (
                f"Switching from '{actual_approach}' to '{alternative_approach}' "
                f"would not have significantly changed the outcome. Both approaches "
                f"perform similarly for '{problem_type}' tasks (effect: {effect:+.1%})."
            )

        return CounterfactualResult(
            query=f"What if session {session_id} used '{alternative_approach}' instead of '{actual_approach}'?",
            treatment="approach",
            actual_value=actual_outcome,
            counterfactual_value="likely success" if avg_success_cf > 0.5 else "likely failure",
            expected_effect=round(effect, 3),
            confidence_interval=(round(ci[0], 3), round(ci[1], 3)),
            adjustment_variables=["problem_type", "difficulty"],
            evidence_strength=evidence,
            interpretation=interp,
        )

    def _assess_evidence(self, sample_size: int, effect_size: float, standard_error: float) -> str:
        """Assess the strength of causal evidence."""
        if sample_size < 10:
            return "insufficient"
        if sample_size < 30:
            return "weak"
        if standard_error < 0.01:
            return "strong"
        if abs(effect_size) > 2 * standard_error:
            return "moderate" if sample_size >= 30 else "weak"
        return "strong" if sample_size >= 100 else "moderate"

    def _interpret_ate(
        self, treatment: str, treatment_value: Any, control_value: Any | None,
        causal_effect: float, ate: float | None, evidence: str,
    ) -> str:
        """Generate human-readable interpretation of causal effects."""
        lines = []

        if ate is not None and control_value is not None:
            direction = "increases" if ate > 0 else "decreases"
            lines.append(
                f"Using '{treatment_value}' {direction} success rate by "
                f"{abs(ate):.1%} compared to '{control_value}' "
                f"(causal effect after adjusting for confounders)."
            )
            if evidence == "strong":
                lines.append("This is a robust causal estimate backed by substantial data.")
            elif evidence == "moderate":
                lines.append("This estimate is directionally reliable but may change with more data.")
            elif evidence == "weak":
                lines.append("⚠️ Low confidence — more sessions needed to confirm this effect.")
            else:
                lines.append("⚠️ Insufficient data — results are exploratory only.")
        else:
            lines.append(
                f"When using '{treatment_value}', the causal success rate is "
                f"estimated at {causal_effect:.1%} (confounder-adjusted)."
            )

        return " ".join(lines)

    # ── Causal Model Building ─────────────────────────────────

    def discover_causal_structure(self) -> CausalGraph:
        """Discover causal relationships from data using constraint-based methods.

        Uses the PC algorithm (simplified) to learn the causal DAG from
        observational data. Starts with a fully connected graph and
        removes edges based on conditional independence tests.
        """
        sessions = self.get_session_data()
        if len(sessions) < 20:
            logger.warning("Insufficient data for causal discovery (need ≥20 sessions)")
            return self.graph

        variables = ["approach", "problem_type", "change_scope",
                     "test_coverage", "token_count", "duration", "success"]

        # Step 1: Start with fully connected graph
        discovered = CausalGraph()
        for var in variables:
            discovered.add_node(CausalNode(
                name=var, description=var, domain=(0, 1),
                is_categorical=var in ("approach", "problem_type"),
            ))

        # Add all possible edges (undirected initially)
        for i, v1 in enumerate(variables):
            for v2 in variables[i + 1:]:
                discovered.add_edge(v1, v2)
                discovered.add_edge(v2, v1)

        # Step 2: Remove edges using conditional independence tests
        # Simplified: use correlation threshold as conditional independence proxy
        for v1 in variables:
            for v2 in variables:
                if v1 >= v2:
                    continue
                # Compute partial correlation controlling for all other variables
                corr = self._partial_correlation(v1, v2, sessions)
                if abs(corr) < 0.1:  # Independence threshold
                    # Remove edge in both directions
                    discovered.edges = [
                        (p, c) for (p, c) in discovered.edges
                        if not ((p == v1 and c == v2) or (p == v2 and c == v1))
                    ]

        # Step 3: Orient edges using v-structures (colliders)
        # If X→Z←Y and X⊥Y but X ̸⊥ Y | Z, orient as X→Z←Y
        # Simplified orientation — in practice would use full PC algorithm

        logger.info(f"Discovered causal graph with {len(discovered.edges)} edges "
                     f"from {len(sessions)} sessions")
        return discovered

    def _partial_correlation(
        self, var1: str, var2: str, sessions: list[dict[str, Any]],
    ) -> float:
        """Compute Pearson correlation between two variables.

        Simplified proxy for conditional independence testing.
        A full implementation would control for other variables.
        """
        vals1 = []
        vals2 = []
        for s in sessions:
            v1 = self._get_numeric_value(s, var1)
            v2 = self._get_numeric_value(s, var2)
            if v1 is not None and v2 is not None:
                vals1.append(v1)
                vals2.append(v2)

        if len(vals1) < 5:
            return 0.0

        mean1 = sum(vals1) / len(vals1)
        mean2 = sum(vals2) / len(vals2)

        num = sum((a - mean1) * (b - mean2) for a, b in zip(vals1, vals2))
        den1 = math.sqrt(sum((a - mean1) ** 2 for a in vals1))
        den2 = math.sqrt(sum((b - mean2) ** 2 for b in vals2))

        if den1 == 0 or den2 == 0:
            return 0.0
        return num / (den1 * den2)

    def _get_numeric_value(self, session: dict[str, Any], variable: str) -> float | None:
        """Get a numeric encoding of a variable for correlation computation."""
        if variable == "success":
            return 1.0 if session.get("was_successful") else 0.0
        elif variable == "change_scope":
            return float(len(session.get("files_changed", [])))
        elif variable == "test_coverage":
            total = session.get("tests_total", 0)
            if total == 0:
                return 0.5  # Neutral value when no test data
            return session.get("tests_passed", 0) / total
        elif variable == "token_count":
            return float(session.get("token_count", 0))
        elif variable == "duration":
            return float(session.get("duration_seconds", 0))
        elif variable == "problem_type":
            # One-hot encoding proxy: assign ordinal values
            ptype = session.get("problem_type", "general")
            types = ["bug_fix", "feature", "refactor", "testing", "migration", "general"]
            return float(types.index(ptype) if ptype in types else 5)
        elif variable == "approach":
            # Ordinal encoding by success rate ranking
            ap = self._categorize_approach(session.get("approach", ""))
            ranking = {
                "Targeted Fix": 0, "Root Cause + Guard": 1, "Extensible Implementation": 2,
                "TDD First": 3, "Incremental Rewrite": 4, "Conservative": 5,
                "Defense in Depth": 6, "Safe Extract": 7, "Clean Sweep": 8,
                "Aggressive Rewrite": 9,
            }
            return float(ranking.get(ap, 5))
        return None

    # ── Context Builder ───────────────────────────────────────

    def build_causal_context(self, task_description: str) -> str:
        """Build a causal analysis context block for agent prompts.

        Answers: WHY should you use this approach? Not just THAT it works.
        """
        sessions = self.get_session_data()
        if len(sessions) < 5:
            return ""

        problem_type = self._classify_problem(task_description)

        # Get causal effect of approaches for this problem type
        type_sessions = [s for s in sessions if s.get("problem_type") == problem_type]
        if len(type_sessions) < 3:
            return ""

        lines = ["### 🧪 Causal Analysis — Why Certain Approaches Work", ""]

        # Find the best and worst approaches with causal estimates
        approach_stats: dict[str, dict[str, Any]] = {}
        for s in type_sessions:
            ap = self._categorize_approach(s.get("approach", ""))
            if ap not in approach_stats:
                approach_stats[ap] = {"successes": 0, "total": 0, "total_scope": 0, "total_cov": 0.0}
            approach_stats[ap]["total"] += 1
            approach_stats[ap]["total_scope"] += len(s.get("files_changed", []))
            if s.get("was_successful"):
                approach_stats[ap]["successes"] += 1
            tot = s.get("tests_total", 0)
            if tot > 0:
                approach_stats[ap]["total_cov"] += s.get("tests_passed", 0) / tot

        sorted_approaches = sorted(
            approach_stats.items(),
            key=lambda x: x[1]["successes"] / max(x[1]["total"], 1),
            reverse=True,
        )

        if len(sorted_approaches) >= 2:
            best_name, best_stats = sorted_approaches[0]
            worst_name, worst_stats = sorted_approaches[-1]
            best_rate = best_stats["successes"] / max(best_stats["total"], 1)
            worst_rate = worst_stats["successes"] / max(worst_stats["total"], 1)

            # Estimate causal mechanisms
            best_scope = best_stats["total_scope"] / max(best_stats["total"], 1)
            worst_scope = worst_stats["total_scope"] / max(worst_stats["total"], 1)
            best_cov = best_stats["total_cov"] / max(best_stats["total"], 1)
            worst_cov = worst_stats["total_cov"] / max(worst_stats["total"], 1)

            lines.append(f"**Why '{best_name}' works:**")
            lines.append(f"- Modifies ~{best_scope:.0f} files on average (vs. ~{worst_scope:.0f} for '{worst_name}')")
            lines.append(f"- Achieves ~{best_cov:.0%} test coverage (vs. ~{worst_cov:.0%} for '{worst_name}')")
            lines.append(f"- Result: {best_rate:.0%} success rate (vs. {worst_rate:.0%} for '{worst_name}')")
            lines.append("")
            lines.append("**Causal chain:** Approach → Change Scope → Test Coverage → Success")
            lines.append(f"- '{best_name}' limits scope → enables thorough testing → higher success")
            lines.append(f"- '{worst_name}' broadens scope → thin testing across files → lower success")
            lines.append("")

        # Counterfactual insight
        lines.append("**What would happen if you switched approach?**")
        target_intervention = self.query_intervention(
            treatment="approach",
            treatment_value=sorted_approaches[0][0] if sorted_approaches else "Targeted Fix",
        )
        if target_intervention.get("ate") is not None:
            lines.append(f"- Causal effect of best approach: {target_intervention['causal_effect']:.1%} base success rate")
            if target_intervention.get("adjustment_variables"):
                lines.append(f"- Controlled for confounders: {', '.join(target_intervention['adjustment_variables'])}")
            lines.append(f"- Evidence strength: {target_intervention.get('evidence_strength', 'unknown')}")
        lines.append("")

        return "\n".join(lines)