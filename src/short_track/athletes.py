"""Athlete stat model and playable roster."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Athlete:
    name: str
    title: str
    color: tuple
    # --- скорость
    v_floor: float = 7.0       # «низкая базовая» скорость при нулевой выносливости, м/с
    v_max: float = 15.5        # потолок скорости при полной выносливости, м/с
    glide: float = 0.025       # как быстро скорость затухает на прямой (1/с)
    # --- выносливость
    stamina_max: float = 100.0
    stamina_regen: float = 0.15        # восстановление, ед/с
    # --- толчки (прямая и старт)
    push_gain: float = 0.90    # прирост скорости от идеального толчка, м/с
    push_cost: float = 1.20    # затраты выносливости на толчок при полной силе
    start_power: float = 1.0   # множитель ускорения на старте
    # --- скрестный шаг (поворот)
    cross_gain: float = 0.45   # прирост скорости от идеального шага, м/с
    cross_opt: float = 0.55    # оптимальный интервал между шагами, с
    cross_tol: float = 0.17    # допуск по интервалу, с
    # --- устойчивость в повороте / управление
    edge_grip: float = 0.88    # доля центростремительной силы, которую держит ребро; снос ∝ (1 - grip)
    lateral_agility: float = 1.0       # насколько быстро смещается при A/D


ROSTER = [
    Athlete("Dae-heon", "Универсал: без слабых мест", (222, 62, 52)),
    Athlete("Stefan", "Спринтер: мощный старт, быстро выдыхается", (52, 112, 226),
            v_max=16.1, stamina_max=80, stamina_regen=0.13, push_gain=1.05,
            push_cost=1.35, start_power=1.2, cross_gain=0.42, cross_opt=0.50,
            cross_tol=0.14, edge_grip=0.86),
    Athlete("Danil", "Стайер: выносливый и ровный", (38, 158, 92),
            v_max=14.9, stamina_max=125, stamina_regen=0.23, push_gain=0.78,
            push_cost=0.95, start_power=0.85, cross_gain=0.45, cross_opt=0.62,
            cross_tol=0.20, edge_grip=0.89, glide=0.02),
    Athlete("Mira", "Технарь: держит ребро, мало сносит", (166, 78, 196),
            v_max=15.8, stamina_max=100, push_gain=0.88, start_power=1.0,
            cross_gain=0.50, cross_opt=0.56, cross_tol=0.22, edge_grip=0.935,
            lateral_agility=1.2),
]
