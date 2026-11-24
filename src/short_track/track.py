"""Track segmentation and conversion from distance/lane to rink coordinates."""
import math

from .config import CURVE_R, HALF_STR, LAP_LEN, MAT_CURVE_INSET, SEG_B, U_MATS


def zone_of(s):
    """('S'|'C', индекс сегмента 0..4) для длины пути s (S — прямая, C — поворот)."""
    s %= LAP_LEN
    if s < SEG_B[0]:
        return "S", 0
    if s < SEG_B[1]:
        return "C", 1
    if s < SEG_B[2]:
        return "S", 2
    if s < SEG_B[3]:
        return "C", 3
    return "S", 4


def mats_limit(s):
    """Максимальное смещение наружу с отступом от матов на виражах."""
    kind, segment = zone_of(s)
    if kind != "C":
        return U_MATS

    start = SEG_B[segment - 1]
    end = SEG_B[segment]
    progress = (s % LAP_LEN - start) / (end - start)
    curve_factor = math.sin(math.pi * progress) ** 2
    return U_MATS - MAT_CURVE_INSET * curve_factor


def track_pos(s, u=0.0):
    """Точка трека: s — путь вдоль линии замера, u — смещение наружу (м).
    Возвращает (x, y, курс). Координаты экранные: x вправо, y ВНИЗ, центр катка = (0, 0)."""
    s %= LAP_LEN
    r = CURVE_R + u
    b0, b1, b2, b3, _ = SEG_B
    if s < b0:                                   # низ, вправо
        return s, r, 0.0
    if s < b1:                                   # правый вираж, вверх
        phi = math.pi / 2 - (s - b0) / CURVE_R
        return HALF_STR + r * math.cos(phi), r * math.sin(phi), phi - math.pi / 2
    if s < b2:                                   # верх, влево
        return HALF_STR - (s - b1), -r, math.pi
    if s < b3:                                   # левый вираж, вниз
        phi = -math.pi / 2 - (s - b2) / CURVE_R
        return -HALF_STR + r * math.cos(phi), r * math.sin(phi), phi - math.pi / 2
    return -HALF_STR + (s - b3), r, 0.0          # низ, вправо до старта
