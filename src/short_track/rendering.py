"""Pygame drawing helpers for the rink, skaters, and HUD."""
import math
from pathlib import Path
import sys
import pygame

from .config import (
    CURVE_LEN, CX, CY, GOLD, H, HALF_STR,
    LAP_LEN, PANEL, SEG_B, U_BLOCKS, W, WHITE,
)
from .track import mats_limit, track_pos
from .utils import clamp

# Независимый масштаб по осям подгоняет модель овала под пропорции фона.
TRACK_SCALE_X = 20.5
TRACK_SCALE_Y = 17.25


def _asset_path(name):
    """Находит ресурс и из исходников, и внутри сборки PyInstaller."""
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)
    else:
        root = Path(__file__).resolve().parents[2]
    return root / "assets" / name


def to_px(x, y):
    return int(CX + x * TRACK_SCALE_X), int(CY + y * TRACK_SCALE_Y)


def lane_poly(u, n=720):
    return [to_px(*track_pos(LAP_LEN * i / n, u)[:2]) for i in range(n)]


def make_font(size, bold=False):
    return pygame.font.SysFont("dejavusans,liberationsans,arial,segoeui,verdana,notosans", size, bold=bold)


def draw_text(surf, font, text, pos, color=WHITE, anchor="topleft", shadow=False):
    img = font.render(text, True, color)
    rect = img.get_rect()
    setattr(rect, anchor, pos)
    if shadow:
        sh = font.render(text, True, (20, 40, 60))
        surf.blit(sh, rect.move(2, 2))
    surf.blit(img, rect)
    return rect


def draw_panel(surf, rect, radius=10):
    p = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(p, PANEL, p.get_rect(), border_radius=radius)
    surf.blit(p, rect.topleft)


def draw_bar(surf, rect, frac, color):
    pygame.draw.rect(surf, (40, 58, 78), rect, border_radius=5)
    inner = pygame.Rect(rect.x, rect.y, int(rect.w * clamp(frac, 0, 1)), rect.h)
    if inner.w > 0:
        pygame.draw.rect(surf, color, inner, border_radius=5)
    pygame.draw.rect(surf, (150, 180, 205), rect, 1, border_radius=5)


def fmt_time(t):
    t = max(t, 0.0)
    return "%02d:%05.2f" % (int(t // 60), t % 60)


def build_track(distance):
    """Берёт готовую арену и поверх неё рисует только гоночную разметку."""
    image = pygame.image.load(str(_asset_path("short_track_arena.png"))).convert()
    surf = pygame.transform.smoothscale(image, (W, H))

    # Внутренняя граница трассы и тонкая линия замера.
    pygame.draw.lines(surf, (65, 125, 190), True, lane_poly(U_BLOCKS), 2)
    pts = lane_poly(0.0, 900)
    for i in range(0, len(pts) - 1, 2):
        pygame.draw.line(surf, (155, 190, 220), pts[i], pts[i + 1], 1)

    # фишки в виражах (по 7 на вираж)
    for seg in (0, 2):
        start = SEG_B[seg] if seg == 0 else SEG_B[2]
        for k in range(7):
            s = start + (k + 0.5) / 7 * CURVE_LEN
            px, py = to_px(*track_pos(s, U_BLOCKS)[:2])
            pygame.draw.circle(surf, (238, 245, 255), (px, py), 6)
            pygame.draw.circle(surf, (214, 52, 46), (px, py), 4)

    # линия старта (красная) и финиша (шахматка)
    a = to_px(*track_pos(0.0, U_BLOCKS)[:2])
    b = to_px(*track_pos(0.0, mats_limit(0.0))[:2])
    pygame.draw.line(surf, (210, 40, 40), a, b, 4)
    sf = distance % LAP_LEN
    cell = 0.3
    for col in range(2):
        s0, s1 = sf - cell + col * cell, sf + col * cell
        outer0, outer1 = mats_limit(s0), mats_limit(s1)
        n_rows = math.ceil((max(outer0, outer1) - U_BLOCKS) / 0.5)
        for i in range(n_rows):
            u0 = U_BLOCKS + i * 0.5
            u1_0, u1_1 = min(u0 + 0.5, outer0), min(u0 + 0.5, outer1)
            if u1_0 <= u0 or u1_1 <= u0:
                continue
            quad = [to_px(*track_pos(s0, u0)[:2]), to_px(*track_pos(s1, u0)[:2]),
                    to_px(*track_pos(s1, u1_1)[:2]), to_px(*track_pos(s0, u1_0)[:2])]
            pygame.draw.polygon(surf, (20, 24, 30) if (i + col) % 2 == 0 else (250, 250, 250), quad)

    return surf


def draw_skater(screen, x, y, heading, color, name, font, speed):
    cx, cy = to_px(x, y)
    L, Wd = 15.0, 7.0                       # полуоси в пикселях (чуть крупнее реальных)
    pts = []
    for k in range(18):
        ang = 2 * math.pi * k / 18
        ex, ey = L * math.cos(ang), Wd * math.sin(ang)
        pts.append((cx + ex * math.cos(heading) - ey * math.sin(heading),
                    cy + ex * math.sin(heading) + ey * math.cos(heading)))
    shadow = [(px + 2, py + 3) for px, py in pts]
    pygame.draw.polygon(screen, (150, 180, 200), shadow)
    pygame.draw.polygon(screen, color, pts)
    pygame.draw.polygon(screen, (20, 30, 44), pts, 2)
    nose = (cx + (L - 2) * math.cos(heading), cy + (L - 2) * math.sin(heading))
    pygame.draw.circle(screen, (250, 240, 220), (int(nose[0]), int(nose[1])), 4)
    pygame.draw.circle(screen, (20, 30, 44), (int(cx), int(cy)), 3)
    draw_text(screen, font, name, (cx, cy - 22), (22, 40, 60), "center")
