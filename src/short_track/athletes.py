"""Athlete stat model and playable roster."""
import sqlite3
from dataclasses import dataclass
from pathlib import Path

ROSTER = []


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
    # доля центростремительной силы, которую держит ребро; снос ∝ (1 - grip)
    edge_grip: float = 0.88
    lateral_agility: float = 1.0       # насколько быстро смещается при A/D


paths = [
    Path("data/game_data.db"),
    Path("ShortTrackSimulator/data/game_data.db"),
]
for path in paths:
    if not path.is_file():
        continue

    try:
        candidate = sqlite3.connect(path)
        candidate.execute("SELECT 1 FROM Athletes LIMIT 1")
        game_data = candidate
        break
    except sqlite3.Error:
        if "candidate" in locals():
            candidate.close()

if game_data is None:
    raise FileNotFoundError("Не найдена подходящая база game_data.db")

cursor = game_data.cursor()
cursor.execute("""SELECT * FROM Athletes""")
athletes = cursor.fetchall()
for athlete in athletes:
    name, title, color, *args = athlete
    color = tuple(int(_) for _ in color.split())
    ROSTER.append(Athlete(name, title, color, *args))

game_data.close()
