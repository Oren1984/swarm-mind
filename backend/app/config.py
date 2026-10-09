"""Simulation configuration.

One frozen config object fully determines a world. The three experimental
worlds differ ONLY in the fields returned by `world_overrides`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

WorldMode = Literal["independent", "collective", "interrupted"]
WORLD_MODES: tuple[WorldMode, ...] = ("independent", "collective", "interrupted")


class SimConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed: int = 1

    # --- arena -----------------------------------------------------------
    width: int = Field(120, ge=40, le=240)
    height: int = Field(80, ge=40, le=160)
    obstacle_count: int = Field(6, ge=0, le=20)
    nest_radius: float = 4.0

    # --- food ------------------------------------------------------------
    food_sources: int = Field(4, ge=1, le=16)
    food_capacity: int = Field(80, ge=1)  # units per source before it relocates
    food_radius: float = 3.0
    food_min_nest_distance: float = 28.0

    # --- agents (shared by every world) -----------------------------------
    agent_count: int = Field(60, ge=1, le=300)
    speed: float = 1.0
    perception_radius: float = 4.0  # food is seen this far beyond a patch edge
    sensor_distance: int = 3  # length of the three forward "antenna" rays
    sensor_angle: float = 0.6  # rad, left/right ray offset
    turn_angle: float = 0.4  # rad, turn applied toward the chosen ray
    heading_noise: float = 0.15  # rad, gaussian wobble per step

    # --- pheromone communication (the experimental mechanism) -------------
    communication: bool = False
    interruption_step: int | None = Field(None, ge=0)
    deposit: float = Field(1.0, ge=0.0, le=5.0)  # "pheromone strength"
    deposit_decay: float = 60.0  # steps; deposit fades with time since pickup
    evaporation: float = Field(0.01, ge=0.0, le=1.0)
    diffusion: float = Field(0.05, ge=0.0, le=0.25)
    pheromone_max: float = 10.0
    choice_k: float = 0.1  # Deneubourg-style choice function (k + c)^n
    choice_n: float = 2.0

    # --- scheduled environment intervention -------------------------------
    obstacle_step: int | None = Field(None, ge=0)
    dynamic_obstacle_length: float = 22.0


def world_overrides(mode: WorldMode, interruption_step: int | None) -> dict:
    """The complete list of parameters allowed to differ between worlds."""
    if mode == "independent":
        return {"communication": False, "interruption_step": None}
    if mode == "collective":
        return {"communication": True, "interruption_step": None}
    if mode == "interrupted":
        return {"communication": True, "interruption_step": interruption_step}
    raise ValueError(f"unknown world mode: {mode}")


def world_config(base: SimConfig, mode: WorldMode, interruption_step: int | None = 1500) -> SimConfig:
    return base.model_copy(update=world_overrides(mode, interruption_step))
