"""Menu, event handling, screens, and the fixed-step application loop."""
import math
import pygame

from .athletes import ROSTER
from .bot import RecordBot
from .config import (
    CX, CY, DISTANCES, DRAFT_BOOST_BUILD_TIME, GOLD, GREEN, H, GRADES,
    LAP_LEN, MAX_SPEED_SCALE, REDC,
    RACE_OPPONENT_COUNTS, START_TIME, W, WHITE, WORLD_RECORDS, YELLOW,
)
from .peloton import Peloton
from .race import Race
from .rendering import (
    build_track, draw_bar, draw_panel, draw_skater,
    draw_text, fmt_time, make_font, to_px
)
from .track import track_pos
from .utils import clamp


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Short Track Simulator")
        self.screen = pygame.display.set_mode((W, H))
        self.clock = pygame.time.Clock()
        self.fonts = {
            "title": make_font(44, True), "big": make_font(40, True),
            "mid": make_font(22, True), "hud": make_font(19, True),
            "small": make_font(15), "tiny": make_font(13),
        }
        # Клавиши: латиница и русская раскладка
        self.keymap = {
            pygame.K_a: "A", ord("ф"): "A", pygame.K_d: "D", ord("в"): "D",
            pygame.K_w: "W", ord("ц"): "W", pygame.K_s: "S", ord("ы"): "S",
            pygame.K_q: "Q", ord("й"): "Q",
            pygame.K_LEFT: "LEFT", pygame.K_RIGHT: "RIGHT",
        }
        # запасной вариант (SDL-сканкоды)
        self.scan = {4: "A", 7: "D", 26: "W", 22: "S", 20: "Q"}
        self.state = "menu"
        self.mode = "solo"
        self.dist_i = 1
        self.ath_i = 0
        self.player_power = 0.7
        self.race = None
        self.bot = None
        self.peloton = None
        self.track_img = {}

    def logical(self, ev):
        name = self.keymap.get(ev.key)
        if name is None:
            name = self.scan.get(getattr(ev, "scancode", None))
        return name

    def start_race(self):
        d = DISTANCES[self.dist_i]
        self.get_track(d)
        if self.mode == "peloton":
            self.bot = None
            self.peloton = Peloton(d, ROSTER[self.ath_i])
            self.race = Race(ROSTER[self.ath_i], d, self.player_power,
                             self.peloton.player_start_offset,
                             self.peloton.player_start_lane)
        else:
            self.race = Race(ROSTER[self.ath_i], d, self.player_power)
            self.bot = RecordBot(d, ROSTER[self.ath_i])
            self.peloton = None
        self.state = "race"

    def get_track(self, distance):
        """Возвращает кэшированный фон арены с разметкой для дистанции."""
        if distance not in self.track_img:
            self.track_img[distance] = build_track(distance)
        return self.track_img[distance]

    def handle(self, ev):
        if ev.type == pygame.QUIT:
            return False
        if self.state == "menu" and ev.type == pygame.KEYDOWN:
            name = self.logical(ev)
            if ev.key == pygame.K_ESCAPE:
                return False
            if ev.key == pygame.K_TAB:
                self.mode = "peloton" if self.mode == "solo" else "solo"
            elif name == "W":
                self.player_power = clamp(self.player_power + 0.05, 0.2, 1.0)
            elif name == "S":
                self.player_power = clamp(self.player_power - 0.05, 0.2, 1.0)
            elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.dist_i = ev.key - pygame.K_1
            elif ev.key == pygame.K_UP:
                self.dist_i = (self.dist_i - 1) % 3
            elif ev.key == pygame.K_DOWN:
                self.dist_i = (self.dist_i + 1) % 3
            elif ev.key == pygame.K_LEFT:
                self.ath_i = (self.ath_i - 1) % len(ROSTER)
            elif ev.key == pygame.K_RIGHT:
                self.ath_i = (self.ath_i + 1) % len(ROSTER)
            elif ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_race()
        elif self.state in ("race", "result"):
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    self.state = "menu"
                elif ev.key in (pygame.K_r, ord("к")):
                    self.start_race()
                elif ev.key == pygame.K_m and self.state == "result":
                    self.state = "menu"
                elif self.state == "race":
                    name = self.logical(ev)
                    if name:
                        self.race.key_down(name)
            elif ev.type == pygame.KEYUP and self.state == "race":
                name = self.logical(ev)
                if name:
                    self.race.key_up(name)
        return True

    def draw_menu(self):
        s = self.screen
        s.blit(self.get_track(DISTANCES[self.dist_i]), (0, 0))
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((12, 26, 42, 150))
        s.blit(veil, (0, 0))
        f = self.fonts
        draw_text(s, f["title"], "SHORT TRACK SIMULATOR",
                  (CX, 84), GOLD, "center", True)
        draw_text(s, f["hud"], "1 / 2 / 3 или ↑↓ — дистанция      ← → — спортсмен      ENTER — старт",
                  (CX, 128), WHITE, "center")
        draw_text(s, f["small"], "W / S — настроить силу толчка до старта: %.0f%%" % (self.player_power * 100),
                  (CX, 158), (190, 220, 240), "center")
        mode_name = ("ПЕЛОТОН · %d соперников" % RACE_OPPONENT_COUNTS[DISTANCES[self.dist_i]]
                     if self.mode == "peloton" else "СОЛО")
        draw_text(s, f["small"], "TAB — режим: %s" % mode_name,
                  (CX, 180), (190, 220, 240), "center")
        # дистанции
        for i, d in enumerate(DISTANCES):
            r = pygame.Rect(0, 0, 200, 64)
            r.center = (CX - 230 + i * 230, 232)
            pygame.draw.rect(s, (255, 196, 66) if i == self.dist_i else (
                40, 62, 86), r, border_radius=12)
            draw_text(s, f["big"], "%d м" % d, r.center, (20, 30,
                      44) if i == self.dist_i else WHITE, "center")
            laps = d / LAP_LEN
            draw_text(s, f["tiny"], "%.1f круга" %
                      laps, (r.centerx, r.bottom + 12), WHITE, "center")
        # спортсмен
        a = ROSTER[self.ath_i]
        box = pygame.Rect(0, 0, 760, 330)
        box.center = (CX, 465)
        draw_panel(s, box, 16)
        pygame.draw.circle(s, a.color, (box.x + 70, box.y + 70), 30)
        pygame.draw.circle(s, (20, 30, 44), (box.x + 70, box.y + 70), 30, 3)
        draw_text(s, f["big"], a.name, (box.x + 125, box.y + 30), GOLD)
        draw_text(s, f["hud"], a.title, (box.x + 125, box.y + 78), WHITE)
        draw_text(s, f["small"], "← →  сменить (%d / %d)" % (self.ath_i + 1,
                  len(ROSTER)), (box.right - 20, box.y + 20), (170, 195, 215), "topright")
        stats = [
            ("Макс. скорость", a.v_max * MAX_SPEED_SCALE, 13.0, 16.0),
            ("Выносливость", a.stamina_max, 70, 130),
            ("Старт", a.start_power, 0.7, 1.3), ("Сила толчка", a.push_gain, 0.7, 1.1),
            ("Скрестный шаг", a.cross_gain, 0.35,
             0.55), ("Допуск ритма Q", a.cross_tol, 0.10, 0.25),
            ("Держит ребро", a.edge_grip, 0.84,
             0.95), ("Подвижность", a.lateral_agility, 0.8, 1.3),
        ]
        for i, (label, val, lo, hi) in enumerate(stats):
            col, row = divmod(i, 4)
            x, y = box.x + 40 + col * 360, box.y + 130 + row * 46
            draw_text(s, f["small"], label, (x, y), WHITE)
            draw_bar(s, pygame.Rect(x + 150, y + 2, 150, 14),
                     (val - lo) / (hi - lo), a.color)
        draw_text(s, f["tiny"], "Оптимальный интервал Q: %.2f с" %
                  a.cross_opt, (box.x + 40, box.bottom - 30), (170, 195, 215))

    def draw_race(self):
        s, f, r = self.screen, self.fonts, self.race
        s.blit(self.track_img[r.distance], (0, 0))

        # Полупрозрачный призрак проходит дистанцию за мировой рекорд.
        record = WORLD_RECORDS[r.distance]
        if self.bot and r.phase != "countdown" and self.bot.s < r.distance:
            ghost_s = self.bot.s
            gx, gy, ghd = track_pos(ghost_s, self.bot.u)
            ghost_layer = pygame.Surface((W, H), pygame.SRCALPHA)
            draw_skater(ghost_layer, gx, gy, ghd, (50, 220, 255),
                        "РЕКОРД", f["tiny"], r.distance / record)
            draw_text(ghost_layer, f["tiny"], self.bot.action,
                      (to_px(gx, gy)[0], to_px(gx, gy)[1] + 22), (40, 180, 220), "center")
            draw_text(ghost_layer, f["tiny"], "%.1f м/с" % self.bot.v,
                      (to_px(gx, gy)[0], to_px(gx, gy)[1] + 36), (40, 180, 220), "center")
            ghost_layer.set_alpha(145)
            s.blit(ghost_layer, (0, 0))

        if self.peloton:
            for opponent in self.peloton.opponents:
                ox, oy, oh = track_pos(opponent.s, opponent.u)
                draw_skater(s, ox, oy, oh, opponent.athlete.color,
                            opponent.name, f["tiny"], opponent.v)

        # след
        if len(r.trail) > 2:
            pts = [to_px(x, y) for x, y in r.trail]
            pygame.draw.lines(s, (120, 160, 190), False, pts, 2)
        x, y, hd = track_pos(r.track_s, r.u)
        draw_skater(s, x, y, hd, r.a.color, r.a.name, f["tiny"], r.v)

        # ---- верхняя левая панель
        p = pygame.Rect(10, 6, 380, 52)
        draw_panel(s, p)
        total_laps = r.distance / LAP_LEN
        lap_now = min(int(r.s // LAP_LEN) + 1, math.ceil(total_laps))
        draw_text(s, f["hud"], "%d м   КРУГ %d / %.1f" %
                  (r.distance, lap_now, total_laps), (p.x + 12, p.y + 6), GOLD)
        draw_text(s, f["hud"], "%s    осталось %d м" % (fmt_time(r.t if r.finish_time is None else r.finish_time),
                                                        max(0, round(r.distance - r.s))), (p.x + 12, p.y + 28), WHITE)
        if self.peloton:
            draw_text(s, f["tiny"], "МЕСТО %d / %d" % (
                self.peloton.player_place(r), len(self.peloton.opponents) + 1),
                (p.right - 8, p.y + 8), (100, 225, 250), "topright")
        else:
            draw_text(s, f["tiny"], "Призрак: мировой рекорд %.3f с" % WORLD_RECORDS[r.distance],
                      (p.right - 8, p.y + 8), (100, 225, 250), "topright")
        # ---- верхняя правая панель (как на макете: Скорость / Линия)
        p = pygame.Rect(W - 400, 6, 390, 84 if self.peloton else 52)
        draw_panel(s, p)
        draw_text(s, f["hud"], "Скорость: %.1f м/с  (%d км/ч)" %
                  (r.v, round(r.v * 3.6)), (p.x + 12, p.y + 6), GOLD)
        line_col = REDC if r.u > 4.6 else YELLOW if r.u < 0.8 else GOLD
        draw_text(s, f["hud"], "Линия: %s" %
                  r.line_name(), (p.x + 12, p.y + 28), line_col)
        if self.peloton:
            saving = self.peloton.player_draft_saving_percent(r)
            draft_label = "АЭРОМЕШОК: экономия %d%%" % saving if saving else "АЭРОМЕШОК: нет"
            draw_text(s, f["tiny"], draft_label,
                      (p.x + 12, p.y + 49), (120, 220, 240))
            boost = r.draft_slingshot
            if boost.cooldown > 0.0:
                boost_hint = "Рывок перезаряжается: %.1f с" % boost.cooldown
            elif boost.in_draft:
                boost_hint = "Заряд готов — смени линию для рывка"
            elif boost.draft_time > 0.0:
                charge = min(100, round(100 * boost.draft_time / DRAFT_BOOST_BUILD_TIME))
                boost_hint = "Заряд рывка: %d%% — держись за соперником" % charge
            else:
                boost_hint = "Держись за соперником, чтобы зарядить рывок"
            draw_text(s, f["tiny"], boost_hint,
                      (p.x + 12, p.y + 65), (180, 210, 230))

        # ---- нижняя левая панель: выносливость и сила толчка
        p = pygame.Rect(10, H - 58, 560, 52)
        draw_panel(s, p)
        st = r.stamina / r.a.stamina_max
        draw_text(s, f["small"], "ВЫНОСЛИВОСТЬ", (p.x + 12, p.y + 5), WHITE)
        draw_bar(s, pygame.Rect(p.x + 150, p.y + 7, 390, 14), st,
                 GREEN if st > 0.5 else YELLOW if st > 0.25 else REDC)
        draw_text(s, f["small"], "СИЛА ТОЛЧКА W/S",
                  (p.x + 12, p.y + 29), WHITE)
        draw_bar(s, pygame.Rect(p.x + 150, p.y + 31, 390, 14),
                 (r.power - 0.2) / 0.8, (110, 170, 240))

        # ---- нижняя правая панель: подсказка по зоне + обратная связь
        p = pygame.Rect(W - 640, H - 58, 630, 52)
        draw_panel(s, p)
        if r.phase in ("run", "start"):
            if r.zone_kind() == "S":
                hint = "ПРЯМАЯ: чередуй A → D; перед поворотом закончи на D"
            else:
                hint = "ПОВОРОТ: Q с ритмом ~%.2f с;  A — внутрь, D — наружу" % r.a.cross_opt
            draw_text(s, f["small"], hint,
                      (p.x + 12, p.y + 6), (190, 215, 235))
        if r.fb_t > 0:
            draw_text(s, f["hud"], r.fb_text, (p.x + 12, p.y + 27), r.fb_color)

        # ---- в инфилде: отрезки + круги и подсказки управления
        p = pygame.Rect(CX - 270, CY + 40, 255, 108)
        draw_panel(s, p)
        draw_text(s, f["small"], "ОТРЕЗКИ + КРУГИ", (p.x + 10, p.y + 6), GOLD)
        for i, (name, dur) in enumerate(r.sectors[-3:][::-1]):
            draw_text(s, f["tiny"], "%s  %.2f" % (name, dur),
                      (p.x + 10, p.y + 28 + i * 16), WHITE)
        for i, lt in enumerate(r.laps[-2:][::-1]):
            draw_text(s, f["tiny"], "Круг %d   %s" % (
                len(r.laps) - i, fmt_time(lt)), (p.x + 10, p.y + 78 + i * 15), (170, 230, 190))
        p = pygame.Rect(CX + 15, CY + 40, 255, 108)
        draw_panel(s, p)
        draw_text(s, f["small"], "УПРАВЛЕНИЕ", (p.x + 10, p.y + 6), GOLD)
        for i, line in enumerate(["A/D — толчки и смещение", "←/→ — смещение на старте", "W/S — сила толчков", "Q — скрестный шаг (поворот)", "R — рестарт   ESC — меню"]):
            draw_text(s, f["tiny"], line, (p.x + 10, p.y + 28 + i * 18), WHITE)

        # ---- центральные сообщения (как на макете)
        if r.phase == "countdown":
            draw_text(s, f["title"], "ГОТОВЬСЬ… %d" %
                      (int(r.cd) + 1), (CX, CY - 85), GOLD, "center", True)
            draw_text(s, f["hud"], "На старте быстро жми A и D строго по очереди",
                      (CX, CY - 50), WHITE, "center")
        elif r.phase == "start":
            draw_text(s, f["title"], "СТАРТ!  ЧЕРЕДУЙ  A  /  D",
                      (CX, CY - 85), GOLD, "center", True)
            draw_text(s, f["hud"], "СИЛА: %d%%  · чередуй A / D; ← внутрь, → наружу · %.0f сек" % (round(r.start_pow * 100), max(0.0, START_TIME - r.t)),
                      (CX, CY - 48), WHITE, "center", True)
        elif r.phase == "finished":
            draw_text(s, f["title"], "ФИНИШ!  %s" % fmt_time(
                r.finish_time), (CX, CY - 85), GOLD, "center", True)
            draw_text(s, f["hud"], "R — ещё раз     M — меню",
                      (CX, CY - 48), WHITE, "center")
        if r.phase == "run" and r.u > 5.0:
            draw_text(s, f["mid"], "МАТЫ РЯДОМ!",
                      (CX, CY - 85), REDC, "center", True)

    def draw_result(self):
        self.draw_race()
        r, s, f = self.race, self.screen, self.fonts
        if self.peloton:
            self.draw_peloton_result()
            return
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((10, 22, 36, 170))
        s.blit(veil, (0, 0))
        box = pygame.Rect(0, 0, 640, 420)
        box.center = (CX, CY)
        draw_panel(s, box, 16)
        avg = r.distance / r.finish_time
        grade = ("Мировой уровень" if avg >= GRADES[0] else "Сборная" if avg >= GRADES[1]
                 else "КМС" if avg >= GRADES[2] else "Разряд" if avg >= GRADES[3] else "Новичок")
        draw_text(s, f["title"], "РЕЗУЛЬТАТ",
                  (box.centerx, box.y + 36), GOLD, "center")
        rows = [
            ("Дистанция / спортсмен", "%d м  •  %s" % (r.distance, r.a.name)),
            ("Время", fmt_time(r.finish_time)),
            ("Средняя скорость", "%.2f м/с  (%.1f км/ч)" % (avg, avg * 3.6)),
            ("Лучший круг", fmt_time(min(r.laps)) if r.laps else "—"),
            ("Выносливость на финише", "%d%%" %
             round(100 * r.stamina / r.a.stamina_max)),
            ("Толчки ≥60%%", "%d из %d" % (r.good_pushes, r.pushes)),
            ("Верные скрестные шаги", "%d из %d" % (r.good_steps, r.steps)),
            ("Удары о маты", "%d" % r.crashes),
        ]
        for i, (k, v) in enumerate(rows):
            draw_text(s, f["hud"], k, (box.x + 40, box.y +
                      90 + i * 31), (180, 205, 225))
            draw_text(s, f["hud"], v, (box.right - 40,
                      box.y + 90 + i * 31), WHITE, "topright")
        draw_text(s, f["mid"], "Оценка: %s" %
                  grade, (box.centerx, box.bottom - 70), GOLD, "center")
        draw_text(s, f["small"], "R — ещё раз     M — меню",
                  (box.centerx, box.bottom - 34), WHITE, "center")

    def draw_peloton_result(self):
        """Показывает итоговую таблицу забега в пелотоне."""
        s, f, r = self.screen, self.fonts, self.race
        veil = pygame.Surface((W, H), pygame.SRCALPHA)
        veil.fill((10, 22, 36, 175))
        s.blit(veil, (0, 0))
        box = pygame.Rect(0, 0, 760, 520)
        box.center = (CX, CY)
        draw_panel(s, box, 16)
        entries = [(r.finish_time, r.a.name + " (ты)", "Игрок", True)]
        entries.extend((op.finish_time, op.name,
                        "%s · %s" % (op.role, op.personality.name), False)
                       for op in self.peloton.opponents)
        entries.sort(key=lambda row: row[0]
                     if row[0] is not None else float("inf"))
        draw_text(s, f["title"], "ИТОГИ ЗАБЕГА · %d м" % r.distance,
                  (box.centerx, box.y + 28), GOLD, "center")
        for place, (time, name, personality, is_player) in enumerate(entries, 1):
            y = box.y + 78 + (place - 1) * 43
            color = GOLD if is_player else WHITE
            time_text = fmt_time(time) if time is not None else "—"
            draw_text(s, f["hud"], "%d." % place, (box.x + 28, y), color)
            draw_text(s, f["hud"], name, (box.x + 76, y), color)
            draw_text(s, f["small"], personality, (box.x + 410, y + 2),
                      (165, 195, 215))
            draw_text(s, f["hud"], time_text,
                      (box.right - 28, y), color, "topright")
        draw_text(s, f["small"], "R — повторить забег     M — меню",
                  (box.centerx, box.bottom - 30), WHITE, "center")

    def run(self):
        STEP = 1.0 / 120.0
        acc = 0.0
        running = True
        while running:
            frame = min(self.clock.tick(60) / 1000.0, 0.1)
            for ev in pygame.event.get():
                if not self.handle(ev):
                    running = False
            if self.state == "race":
                acc += frame
                while acc >= STEP:
                    if self.peloton:
                        self.peloton.update(STEP, self.race)
                        draft = self.peloton.player_draft_strength(self.race)
                        self.race.update(STEP, draft)
                        self.peloton.resolve_contacts(self.race)
                    else:
                        self.race.update(STEP)
                        self.bot.update(STEP, self.race)
                    acc -= STEP
                race_stopped = (self.race.phase == "finished"
                                and self.race.fb_t <= 0 and self.race.v < 0.5)
                pack_finished = self.peloton is None or self.peloton.all_finished
                if race_stopped and pack_finished:
                    self.state = "result"
            if self.state == "menu":
                self.draw_menu()
            elif self.state == "race":
                self.draw_race()
            else:
                self.draw_result()
            pygame.display.flip()
        pygame.quit()
