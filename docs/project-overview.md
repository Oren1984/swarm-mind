# Project overview

## The idea in one paragraph

An ant colony has no manager, yet it finds food and builds efficient trails. Each ant follows a few simple rules and reacts to chemical marks left by others. Swarm Mind rebuilds a stripped-down version of that mechanism in software and then treats it as an experiment: the same world is run with and without the chemical channel, across many random scenarios, and the difference is measured.

## Why build it

Swarm intelligence demos are common, and most of them show one attractive run. That leaves the interesting questions open. Is the trail doing any work, or would the agents have done as well without it? Does the result survive a different random seed? When does the mechanism fail? This project is organized around those questions rather than around the animation.

It is the fourth in a small series of research demonstrations:

1. Butterfly World Model — how can a system predict the future?
2. Artificial Life, the Learning Creature — how can learning emerge?
3. Causal Universe, What If? — what causes what?
4. **Swarm Mind — how can collective behaviour emerge without a leader?**

## Questions

**Primary:** can indirect local communication improve collective problem-solving and environmental adaptation compared with independent agents?

**Secondary:**

1. Can decentralized agents establish recognizable shared foraging trails?
2. Does pheromone-mediated coordination improve food collection?
3. How does the group behave when communication is disrupted?
4. Can the swarm adapt when its environment changes?
5. Under which conditions does collective communication fail to provide an advantage?

The answers this simulation gives are in [results-and-limitations.md](results-and-limitations.md). In short: yes to 1 and 2 under default conditions; the advantage disappears when communication is cut (3); adaptation to a new wall is partial (4); and the advantage shrinks, and in one tested condition reverses, when pheromone information goes stale (5).

## What is in scope

- One bounded 2-D arena with a nest, food sources, walls and a pheromone grid.
- One simulation engine, run in three configurations side by side.
- An interactive dashboard that draws the engine's state and lets you intervene.
- A reproducible multi-seed experiment runner with stored results.
- Tests that check both the software and the fairness of the comparison.

## What is deliberately out of scope

- Biological realism. No species, no calibrated parameters, no physiology.
- The Ant System optimization algorithm, or any benchmark such as the traveling salesman problem.
- A flocking (Boids) engine.
- Large language models, cloud services, databases, authentication, CI/CD, orchestration.
- Any claim about intelligence in general.

## Terms used throughout

| Term | Meaning here |
|---|---|
| Agent | One simulated forager. It has a position, a heading, and a flag for carrying food. |
| Pheromone | A number per grid cell. Carriers add to it; it evaporates and spreads slightly each step. |
| Stigmergy | Coordination through marks left in the environment instead of direct messages. |
| Nest scent | A homing cue all agents share in all worlds: the walking distance to the nest, sensed locally. |
| Seed | The integer that determines the map, food sites, starting agents and every random choice. |
| Controlled scenario | A run with default parameters and no manual intervention. |
| Exploratory mode | Any run where you changed a parameter or intervened by hand. The dashboard labels it. |
| Synthetic data | Data produced by the simulator. The measurements are real, but they are measurements of the simulation. |
