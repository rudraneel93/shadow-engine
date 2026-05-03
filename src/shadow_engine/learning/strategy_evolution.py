"""Self-Modifying Strategy Evolution — Breakthrough Feature #6.

Uses genetic algorithms to evolve the Laboratory's strategy templates over time.
Strategies that perform well mutate and reproduce; poorly performing ones die off.

Over hundreds of sessions, the system evolves strategies OPTIMALLY TUNED to YOUR
specific codebase — a recursive self-improvement loop that no competitor has.

Process:
  1. Seed with 12 hardcoded strategies (current STRATEGIES_BY_PROBLEM)
  2. After each batch: mutate best strategies, crossover successful pairs
  3. Selection: keep top-N, discard bottom performers
  4. Track lineage: "Extensible Design v3.2 — evolved from v2.1 after 47 sessions"
  5. Cross-pollinate: bug_fix strategies tested on refactor tasks
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any

import logging

logger = logging.getLogger(__name__)


# ── Strategy Genome ─────────────────────────────────────────────

@dataclass
class StrategyGene:
    """A single instruction fragment in a strategy genome."""
    text: str
    weight: float = 1.0  # How important this instruction is (evolves over time)

    def mutate(self, mutation_rate: float = 0.1) -> "StrategyGene":
        """Mutate this gene with small random changes."""
        if random.random() < mutation_rate:
            # Word substitution
            words = self.text.split()
            if len(words) > 2:
                idx = random.randint(0, len(words) - 1)
                synonyms = {
                    "minimal": ["smallest", "least", "fewest"],
                    "comprehensive": ["thorough", "complete", "full"],
                    "focused": ["targeted", "precise", "specific"],
                    "test": ["verify", "validate", "check"],
                    "implement": ["build", "create", "develop"],
                    "refactor": ["restructure", "reorganize", "clean up"],
                    "analyze": ["examine", "investigate", "study"],
                    "fix": ["resolve", "correct", "repair"],
                }
                if words[idx] in synonyms:
                    words[idx] = random.choice(synonyms[words[idx]])
                    return StrategyGene(text=" ".join(words), weight=self.weight)

        if random.random() < mutation_rate * 0.5:
            # Weight perturbation
            new_weight = self.weight + random.uniform(-0.1, 0.1)
            return StrategyGene(text=self.text, weight=max(0.1, min(2.0, new_weight)))

        return StrategyGene(text=self.text, weight=self.weight)


@dataclass
class StrategyGenome:
    """A complete strategy as a collection of instruction genes."""
    name: str
    problem_type: str
    genes: list[StrategyGene]  # Ordered list of instruction fragments
    generation: int = 0
    parent_ids: list[str] = field(default_factory=list)  # Lineage tracking
    fitness_history: list[float] = field(default_factory=list)

    def to_approach_text(self) -> str:
        """Convert genome to approach text suitable for experiment prompt."""
        sorted_genes = sorted(self.genes, key=lambda g: g.weight, reverse=True)
        return " ".join(g.text for g in sorted_genes)

    def to_strategy_dict(self) -> dict[str, str]:
        """Convert to the format expected by ExperimentRunner."""
        return {
            "name": f"{self.name} v{self.generation}",
            "approach": self.to_approach_text(),
        }

    def mutate(self, mutation_rate: float = 0.15) -> "StrategyGenome":
        """Create a mutated copy of this genome."""
        mutated_genes = [g.mutate(mutation_rate) for g in self.genes]

        # Gene insertion (low probability)
        if random.random() < mutation_rate and len(mutated_genes) < 10:
            new_gene = StrategyGene(text=random.choice([
                "Add comprehensive error handling.",
                "Write unit tests for all new code paths.",
                "Document complex logic with clear comments.",
                "Keep changes minimal and focused.",
                "Verify existing tests still pass.",
                "Consider edge cases and null inputs.",
            ]))
            mutated_genes.insert(random.randint(0, len(mutated_genes)), new_gene)

        # Gene deletion (low probability)
        if random.random() < mutation_rate * 0.5 and len(mutated_genes) > 2:
            mutated_genes.pop(random.randint(0, len(mutated_genes) - 1))

        return StrategyGenome(
            name=self.name,
            problem_type=self.problem_type,
            genes=mutated_genes,
            generation=self.generation + 1,
            parent_ids=[f"{self.name}_v{self.generation}"],
        )


def crossover(parent1: StrategyGenome, parent2: StrategyGenome) -> StrategyGenome:
    """Create a child genome by combining genes from two parents."""
    # Take first half from parent1, second half from parent2
    split1 = len(parent1.genes) // 2 if parent1.genes else 0
    split2 = len(parent2.genes) // 2 if parent2.genes else 0
    child_genes = parent1.genes[:split1] + parent2.genes[split2:]
    if not child_genes:
        child_genes = parent1.genes if parent1.genes else parent2.genes

    return StrategyGenome(
        name=f"Hybrid_{parent1.name}_{parent2.name}"[:50],
        problem_type=parent1.problem_type,
        genes=[StrategyGene(text=g.text, weight=g.weight) for g in child_genes],
        generation=max(parent1.generation, parent2.generation) + 1,
        parent_ids=[f"{parent1.name}_v{parent1.generation}",
                     f"{parent2.name}_v{parent2.generation}"],
    )


# ── Seed Strategies (from current STRATEGIES_BY_PROBLEM) ────────

SEED_STRATEGIES: dict[str, list[StrategyGenome]] = {
    "bug_fix": [
        StrategyGenome("bug_fix", "bug_fix", [
            StrategyGene("Analyze the error precisely."),
            StrategyGene("Find the minimal code change needed."),
            StrategyGene("Write a focused fix with a regression test."),
            StrategyGene("Do not refactor unrelated code."),
        ]),
        StrategyGenome("bug_fix", "bug_fix", [
            StrategyGene("Find the root cause of the bug."),
            StrategyGene("Fix it, then add input validation or guard clauses."),
            StrategyGene("Add both unit and integration tests."),
        ]),
        StrategyGenome("bug_fix", "bug_fix", [
            StrategyGene("Fix the bug."),
            StrategyGene("Add comprehensive error handling at every layer."),
            StrategyGene("Add logging for observability."),
            StrategyGene("Write tests at unit and integration levels."),
        ]),
    ],
    "feature": [
        StrategyGenome("feature", "feature", [
            StrategyGene("Implement the feature with minimal code necessary."),
            StrategyGene("Prioritize simplicity and test coverage."),
        ]),
        StrategyGenome("feature", "feature", [
            StrategyGene("Implement with a clean interface design."),
            StrategyGene("Structure code for future extension."),
            StrategyGene("Write thorough tests."),
        ]),
        StrategyGenome("feature", "feature", [
            StrategyGene("Implement with complete error handling."),
            StrategyGene("Cover edge cases."),
            StrategyGene("Add logging."),
            StrategyGene("Write comprehensive tests."),
            StrategyGene("Follow existing patterns closely."),
        ]),
    ],
    "refactor": [
        StrategyGenome("refactor", "refactor", [
            StrategyGene("Extract core logic into smaller functions."),
            StrategyGene("Keep external API unchanged."),
            StrategyGene("Verify with existing tests."),
        ]),
        StrategyGenome("refactor", "refactor", [
            StrategyGene("Refactor to match prevailing codebase patterns."),
            StrategyGene("Study similar modules and align structure."),
            StrategyGene("Preserve all behavior."),
        ]),
        StrategyGenome("refactor", "refactor", [
            StrategyGene("Extract functions."),
            StrategyGene("Improve naming."),
            StrategyGene("Reduce duplication."),
            StrategyGene("Add docstrings."),
            StrategyGene("Update tests to match new structure."),
        ]),
    ],
    "general": [
        StrategyGenome("general", "general", [
            StrategyGene("Make minimal, targeted changes."),
            StrategyGene("Prioritize correctness and test coverage."),
            StrategyGene("Follow existing codebase conventions."),
        ]),
        StrategyGenome("general", "general", [
            StrategyGene("Balance core problem and surrounding code."),
            StrategyGene("Make reasonable refactors for clarity."),
        ]),
        StrategyGenome("general", "general", [
            StrategyGene("Solve problem thoroughly."),
            StrategyGene("Improve related code."),
            StrategyGene("Consider edge cases."),
            StrategyGene("Add comprehensive tests."),
            StrategyGene("Document your reasoning."),
        ]),
    ],
}


# ── Evolution Engine ────────────────────────────────────────────

class StrategyEvolutionEngine:
    """Genetic algorithm engine for evolving strategy templates."""

    def __init__(self, store: Any):
        self.store = store
        self._population: dict[str, list[StrategyGenome]] = {
            pt: list(genomes) for pt, genomes in SEED_STRATEGIES.items()
        }
        self._fitness_cache: dict[str, float] = {}
        self.generation: int = 0

    def evolve(self, problem_type: str, num_survivors: int = 5) -> list[StrategyGenome]:
        """Run one generation of evolution for a problem type.

        Returns the new population after selection, crossover, and mutation.
        """
        population = self._population.get(problem_type, [])
        if not population:
            population = SEED_STRATEGIES.get(problem_type, SEED_STRATEGIES["general"])
            self._population[problem_type] = list(population)

        # Compute fitness for all genomes
        fitnesses = [self._compute_fitness(g) for g in population]

        # Selection: keep top survivors
        ranked = sorted(
            zip(population, fitnesses), key=lambda x: x[1], reverse=True
        )
        survivors = [g for g, _ in ranked[:num_survivors]]

        # Crossover: create children from top pairs
        children: list[StrategyGenome] = []
        for i in range(min(len(survivors) - 1, num_survivors // 2)):
            if i + 1 < len(survivors):
                child = crossover(survivors[i], survivors[i + 1])
                children.append(child)

        # Mutation: mutate survivors
        mutants = [g.mutate(0.15) for g in survivors[:num_survivors // 2]]

        # New population
        new_population = survivors + children + mutants
        if len(new_population) > 15:
            new_population = new_population[:15]

        self._population[problem_type] = new_population
        self.generation += 1

        logger.info(f"Evolved {problem_type} strategies: {len(population)} → "
                     f"{len(new_population)} (gen {self.generation})")

        return new_population

    def _compute_fitness(self, genome: StrategyGenome) -> float:
        """Compute fitness score for a genome based on session outcomes.

        Fitness = rolling success rate × recency weight × diversity bonus
        """
        cache_key = genome.to_approach_text()[:80]
        if cache_key in self._fitness_cache:
            return self._fitness_cache[cache_key]

        conn = self.store._get_conn() if hasattr(self.store, "_get_conn") else None
        if conn is None:
            return 0.5

        # Get sessions using this approach
        rows = conn.execute(
            "SELECT outcome, created_at FROM sessions "
            "WHERE approach LIKE ? AND outcome != 'in_progress' "
            "ORDER BY created_at DESC LIMIT 50",
            (f"%{genome.name}%",),
        ).fetchall()

        if not rows:
            # No data yet — use parent fitness if available
            if genome.fitness_history:
                return genome.fitness_history[-1]
            return 0.5

        successes = sum(1 for r in rows if r["outcome"] == "success")
        base_rate = successes / len(rows) if rows else 0.5

        # Recency bonus: recent successes weighted more
        recency_weight = 0.0
        for i, r in enumerate(rows[:10]):
            if r["outcome"] == "success":
                recency_weight += 1.0 / (i + 1)
        recency_bonus = recency_weight / max(1, len(rows[:10])) * 0.2

        # Diversity bonus: reward genomes that differ from population
        diversity = 0.0
        pop = self._population.get(genome.problem_type, [])
        if pop:
            other_fitnesses = [self._fitness_cache.get(g.to_approach_text()[:80], 0.5)
                              for g in pop if g != genome]
            if other_fitnesses:
                diversity = 1.0 - (base_rate / max(other_fitnesses)) if max(other_fitnesses) > 0 else 0.0
                diversity = max(0.0, min(0.3, diversity))

        fitness = min(1.0, base_rate + recency_bonus + diversity * 0.1)
        self._fitness_cache[cache_key] = fitness
        genome.fitness_history.append(fitness)
        return fitness

    def get_best_strategies(self, problem_type: str, top_n: int = 3) -> list[dict[str, str]]:
        """Get the best evolved strategies for a problem type."""
        population = self._population.get(problem_type, SEED_STRATEGIES.get(problem_type, []))
        fitnesses = [(g, self._compute_fitness(g)) for g in population]
        ranked = sorted(fitnesses, key=lambda x: x[1], reverse=True)
        return [g.to_strategy_dict() for g, _ in ranked[:top_n]]

    def get_evolution_report(self) -> str:
        """Generate a report on strategy evolution."""
        lines = ["=" * 70]
        lines.append("  STRATEGY EVOLUTION REPORT")
        lines.append("=" * 70)
        lines.append(f"Generation: {self.generation}")
        lines.append("")

        for pt, pop in self._population.items():
            if not pop:
                continue
            lines.append(f"--- {pt.upper()} ---")
            ranked = sorted(
                [(g, self._compute_fitness(g)) for g in pop],
                key=lambda x: x[1], reverse=True,
            )
            for i, (genome, fitness) in enumerate(ranked[:5]):
                emoji = "🏆" if i == 0 else "  "
                lines.append(f"  {emoji} {genome.name} v{genome.generation}: "
                             f"fitness={fitness:.3f}")
                if genome.parent_ids:
                    lines.append(f"     Parents: {', '.join(genome.parent_ids)}")
            lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)

    def get_evolved_strategies_dict(self) -> dict[str, list[dict[str, str]]]:
        """Get all evolved strategies in the format expected by ExperimentRunner."""
        result: dict[str, list[dict[str, str]]] = {}
        for pt in SEED_STRATEGIES:
            result[pt] = self.get_best_strategies(pt, top_n=3)
        return result