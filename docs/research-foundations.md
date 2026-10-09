# Research foundations

This document separates four things that are easy to blur:

1. what the original researchers reported,
2. which of their principles this proof of concept implements,
3. what our own simulation measured,
4. what remains unsupported or out of scope.

## Research & transparency statement

Swarm Mind is a research-inspired proof of concept built using synthetic simulation environments and locally implemented agent-based rules.

No large language model is used for agent control, collective decision-making, simulation, or experimental evaluation. Agents are moved by about forty lines of array arithmetic in `backend/app/simulation/agents.py`.

The project explores selected concepts from self-organization, stigmergy, and decentralized coordination. Its results describe the behaviour of this specific simulated system under controlled conditions. They are not a general proof of intelligence and not a validation of biological behaviour.

The implementation intentionally simplifies the original research models. The simplifications are listed per paper below. An LLM layer that explains runs in plain language would be an optional future extension; it is not needed for the scientific purpose and is not implemented.

**"Synthetic" has a precise meaning here.** Maps, agents and food are generated from a seed; nothing was observed in the real world. The numbers in the results are nevertheless real measurements: they were produced by running the simulator, they are stored, and they can be regenerated. They are evidence about the simulator.

## How the references were verified

Access date: 9 October 2026.

| Reference | What was checked | Source of the check |
|---|---|---|
| Deneubourg et al. 1990 | Title, authors, journal, volume, issue, pages, year. Abstract content. | Crossref metadata record for the DOI; the abstract as shown on the publisher's DOI landing page (via search result). **The full text was not accessible** (publisher login redirect), so statements below rely on the abstract only. |
| Dorigo et al. 1996 | Title, authors, journal, volume, issue, pages, year. Abstract content. | Crossref metadata record for the DOI; the abstract as indexed. **The full text on IEEE Xplore was not read**; statements below rely on the abstract only. |
| Reynolds 1987 | Title, author, venue, volume, number, pages, year. Abstract. | The author's own page (open access) and the Crossref record for the ACM DOI. Only the abstract page was read, not the full paper. |

All three DOIs resolve. Bibliographic details below match Crossref.

---

## Paper A — Deneubourg, Aron, Goss & Pasteels (1990)

**Reference.** Deneubourg, J.-L., Aron, S., Goss, S., & Pasteels, J. M. (1990). The self-organizing exploratory pattern of the Argentine ant. *Journal of Insect Behavior*, 3(2), 159–168. https://doi.org/10.1007/BF01417909

**Original question.** How do Argentine ant workers form a collective exploratory trail pattern when entering unmarked territory?

**Relevant mechanism.** Individual workers lay trail pheromone and follow it. Recruitment toward an advancing front produces a trail back to the nest.

**What the original work demonstrated (per its abstract).** Workers first explore chemically unmarked ground at random; as the front advances, further explorers are recruited and a trail extends from the front to the nest; unlike trails between two fixed points, the exploratory trail has no fixed destination and resembles army-ant foraging patterns; a minimal model shows the pattern can arise from the workers' simple trail-laying and trail-following behaviour — an example of self-organization.

**What this proof of concept implements.**

- Trail-laying and trail-following as purely individual, local rules.
- A probabilistic choice among directions weighted by `(k + c)^n`, where `c` is local pheromone. This functional form is the one commonly attributed to the Deneubourg group's ant choice models; we use `k = 0.1`, `n = 2`, chosen by us.
- Random exploration when no pheromone is sensed.

**What is simplified or omitted.**

- Our trails connect a nest and food sources. The paper's subject is an *exploratory* trail with no fixed destination. We do not reproduce that pattern.
- In our model only food carriers deposit pheromone. Exploring ants in the paper lay trail while exploring.
- No species-specific parameters, no ant density effects, no recruitment at the nest.
- Our agents have a shared "nest scent" homing cue with no counterpart in the paper.

**Which experiment tests the adopted principle.** Experiment 2 (trail emergence) and Experiment 1 (does following trails matter).

**Our results.** With deposition and following switched on, the busiest 5% of cells carried 56.7% of agent traffic (independent agents: 17.0%; paired difference +39.6 points, 95% interval +36.7 to +42.9; higher in 20 of 20 seeds). Shared routes form without any routing code.

**Interpretation and limits.** This shows that, in this simulator, local laying-and-following rules are sufficient for traffic to concentrate on shared routes. It does not test the paper's model, does not reproduce its exploratory pattern, and says nothing about Argentine ants.

---

## Paper B — Dorigo, Maniezzo & Colorni (1996)

**Reference.** Dorigo, M., Maniezzo, V., & Colorni, A. (1996). Ant system: optimization by a colony of cooperating agents. *IEEE Transactions on Systems, Man, and Cybernetics, Part B (Cybernetics)*, 26(1), 29–41. https://doi.org/10.1109/3477.484436

**Original question.** Can an analogy with ant colonies yield a useful method for stochastic combinatorial optimization?

**Relevant mechanism.** Artificial ants construct solutions step by step, choosing components probabilistically according to pheromone and a greedy heuristic; pheromone is reinforced on good solutions and evaporates.

**What the original work demonstrated (per its abstract).** It proposes Ant System as a new approach to stochastic combinatorial optimization characterized by positive feedback (rapid discovery of good solutions), distributed computation (avoiding premature convergence) and a constructive greedy heuristic (acceptable solutions early), applies it to the traveling salesman problem and reports simulation results.

**What this proof of concept implements.**

- Indirect communication through a shared pheromone medium.
- Positive feedback: successful trips deposit pheromone, which attracts more trips.
- Evaporation, so unused information decays.
- Probabilistic rather than greedy choice.
- Many simple agents computing in parallel with no coordinator.

**What is simplified or omitted — the adaptation, stated explicitly.**

| Ant System (as described in the abstract) | Swarm Mind |
|---|---|
| Solves a formal optimization problem (TSP) on a graph. | Agents forage in continuous 2-D space. There is no problem instance, no tour, no objective function being minimized. |
| Ants build complete solutions; pheromone update depends on solution quality. | Pheromone is deposited continuously while walking home; its strength depends only on time since pickup. |
| A greedy heuristic (e.g. closeness of the next city) is combined with pheromone. | No heuristic term. The nearest analogue is "head for food you can see". |
| Performance is compared with other optimization methods. | Performance is compared only with the same agents without pheromone. |

**This is not an implementation of Ant System and not a benchmark of it.** We borrow its vocabulary of mechanisms, not its algorithm.

**Which experiment tests the adopted principles.** Experiment 1 (positive feedback and delivery), Experiment 3 (remove the channel), Experiment 6 (evaporation sweep).

**Our results.** Collective agents delivered 1,279 units on average against 561 (+718; 95% interval +681 to +757; 20 of 20 seeds). Removing the channel mid-run removed the advantage (302 versus 654 in the second half). Evaporation mattered in both directions: the effect was largest at the default 1% per step (+128%), smaller at 0.2% (+89%), 5% (+95%), 20% (+13%) and with no evaporation at all (+35%). With no evaporation *and* fast-moving food, the collective swarm did 4% worse than independent agents (−25 units; interval −47 to −3; better in only 5 of 20 seeds).

**Interpretation and limits.** Within this simulator, pheromone positive feedback raises foraging throughput, and evaporation is necessary to keep the shared information current — qualitatively in line with the roles the abstract assigns to those mechanisms. Nothing here measures optimization quality, convergence, or performance on any standard problem, and the abstract's claim about distributed computation avoiding premature convergence is **not tested**.

---

## Paper C — Reynolds (1987), conceptual reference

**Reference.** Reynolds, C. W. (1987). Flocks, herds and schools: A distributed behavioral model. *Computer Graphics*, 21(4) (SIGGRAPH '87 Conference Proceedings), 25–34. https://doi.org/10.1145/37402.37406 — author's page: https://www.red3d.com/cwr/papers/1987/boids.html

**Original question.** How can the aggregate motion of a flock be animated without scripting each bird's path?

**Relevant mechanism.** Each simulated bird is an independent actor that steers according to its local perception of its surroundings.

**What the original work demonstrated (per its abstract).** A flock simulated as a particle system of independent actors, each navigating by local perception, simulated physics and programmed behaviours, produces aggregate flock motion as the result of the dense interaction of relatively simple individual behaviours.

**What this proof of concept implements.** Only the general principle: each agent acts on local perception, and group-level patterns are not programmed anywhere.

**What is omitted.** Everything specific to flocking. Our agents do not perceive each other at all — they interact only through the pheromone field. There is no separation, alignment or cohesion, and no Boids engine. Adding one would have been scope expansion without a research need.

**Which experiment tests the adopted principle.** Experiment 2, loosely: a group-level pattern (trails) appears though no rule mentions trails.

**Interpretation and limits.** Reynolds' work is cited as intellectual context for "global pattern from local rules". No result of this project should be read as evidence about flocking.

---

## Research-to-implementation map

| Concept | Source | Where in the code | Evidence in this project | Not covered |
|---|---|---|---|---|
| Decentralized control, local perception only | A, C | `agents.decide` takes only an `Observation`; `World.observe` builds it from cells near the agent | Integrity test on the function signature and source; trails form without routing code | The shared nest scent is a non-local convenience (documented) |
| Trail laying | A, B | deposit block in `World.step` | Unit tests; Experiment 2 | Exploratory trail laying by non-carriers |
| Probabilistic trail following | A, B | `(k + c)^n` weighting in `agents.decide` | Unit tests on choice frequencies; Experiment 1 | Fitting `k`, `n` to data |
| Positive feedback | B | emerges from deposit + follow | Experiment 1; Experiment 3 (remove it) | Formal analysis of feedback gain |
| Evaporation | B | `World._evaporate` | Unit test; Experiment 6 sweep | — |
| Stigmergy (communication through the environment) | A, B | agents never read each other's state | World B with deposit 0 is identical to World A (integrity test) | — |
| Self-organized spatial structure | A, C | none — it is an outcome | Traffic concentration metric; `traffic_maps.png` | Reproducing any specific published pattern |
| Robustness to losing the channel | motivated by B | `World.disable_communication` | Experiment 3 | — |
| Adaptation to environmental change | motivated by A, B | `World.add_obstacle_segment`, food relocation | Experiment 4; Experiment 6 (`food_capacity`) | Shortest-path selection (the classic "double bridge" result) is **not** tested |
| Combinatorial optimization | B | — | — | Entirely out of scope |
| Flocking | C | — | — | Entirely out of scope |

## Claims this project does not support

- That real ants behave like these agents.
- That pheromone communication is beneficial in general. It was beneficial under most tested conditions and harmful under one.
- That the swarm finds shortest or optimal routes. Route optimality was not measured.
- That this constitutes intelligence, general or otherwise.
- Anything about the relative merit of Ant System as an optimization method.
