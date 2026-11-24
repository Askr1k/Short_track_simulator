"""Player race state, input handling, and skating physics."""
import math
from collections import deque

from .config import (
    ACTION_MISS_SPEED_COST, ACTION_MISS_STAMINA_COST, BASE_STAMINA_DRAIN,
    COUNTDOWN, CROSS_STEP_MISS_COST, CROSS_STEP_STAMINA_COST,
    CURVE_CONTROL_STAMINA_DRAIN, CURVE_R, DRAFT_BOOST_DURATION,
    DRAFT_BOOST_STAMINA_COST, DRAFT_MAX_SAVING,
    DRAFT_SPEED_DRAG_REDUCTION,
    INWARD_KEY, LAT_ACC, LAP_LEN,
    MAX_SPEED_SCALE, OUTWARD_KEY,
    PUSH_STAMINA_SCALE,
    SECTOR_NAMES, START_ACC, START_RATE_FULL, START_TIME, STRAIGHT_DRAG,
    START_STAMINA_DRAIN, STAMINA_CAP_EXP, STRAIGHT_PUSH_IMPULSE, U_BLOCKS,
)
from .track import mats_limit, track_pos, zone_of
from .drafting import DraftSlingshot
from .utils import clamp, smoothstep

class Race:
    """Состояние и физика одного заезда. Ввод — логические клавиши 'A','D','W','S','Q'."""

    def __init__(self, athlete, distance, initial_power=0.7,
                 track_offset=0.0, initial_u=0.35):
        self.a = athlete
        self.distance = distance
        self.track_offset = track_offset
        self.phase = "countdown"          # countdown → start → run → finished
        self.cd = COUNTDOWN
        self.t = 0.0                      # время гонки
        self.s = 0.0                      # пройдено по линии замера, м
        self.u = initial_u                # смещение от линии замера (внутрь < 0 < наружу)
        self.w = 0.0                      # боковая скорость (наружу > 0)
        self.v = 0.0                      # скорость, м/с
        self.stamina = athlete.stamina_max
        self.draft_slingshot = DraftSlingshot()
        self.power = clamp(initial_power, 0.2, 1.0)  # сила толчков (W/S)
        self.down = {}                    # удерживаемые клавиши → время нажатия
        self.press_zone = {}
        self.last_push_key = None
        self.last_push_t = -9.0
        self.next_push_key = "A"
        self.last_push_dv = 0.0
        self.last_push_q_alt = 1.0
        self.last_q_t = None
        self.last_q_interval = None
        self.start_rate = 0.0
        self.start_pow = 0.0
        self.last_alt_key = None
        self.last_alt_t = -9.0
        self.laps = []
        self.lap_t0 = 0.0
        self.lap_idx = 0
        self.sectors = []
        self.sector_t0 = 0.0
        self.cur_zone = zone_of(self.track_s)[1]
        self.fb_text, self.fb_color, self.fb_t = "", (255, 255, 255), 0.0
        self.crashes = 0
        self.crash_cd = 0.0
        self.finish_time = None
        self.trail = deque(maxlen=60)
        self._trail_t = 0.0
        self.speed_log = []
        self.good_pushes = 0
        self.pushes = 0
        self.good_steps = 0
        self.steps = 0
        self.exhausted = False

    # ------------------------------------------------------------- утилиты
    @property
    def track_s(self):
        """Координата стартового места по овалу; s при этом остаётся личным прогрессом."""
        return self.s + self.track_offset

    def zone_kind(self):
        return zone_of(self.track_s)[0]

    def v_cap(self):
        """Потолок скорости: растёт с выносливостью, при нуле — низкая база."""
        a = self.a
        f = (max(self.stamina, 0.0) / a.stamina_max) ** STAMINA_CAP_EXP
        max_speed = a.v_max * MAX_SPEED_SCALE
        return a.v_floor + (max_speed - a.v_floor) * f

    def headroom(self):
        """0..1 — сколько запаса до потолка скорости (прибавки гаснут у потолка)."""
        cap = self.v_cap()
        return clamp((cap - self.v) / max(cap - self.a.v_floor, 0.5), 0.0, 1.0)

    def say(self, text, color=(255, 255, 255), ttl=1.2):
        self.fb_text, self.fb_color, self.fb_t = text, color, ttl

    def line_name(self):
        if self.u < 0.8:
            return "ВНУТРЕННЯЯ (у фишек)"
        if self.u < 2.6:
            return "СРЕДНЯЯ"
        if self.u < 4.6:
            return "ВНЕШНЯЯ"
        return "У МАТОВ!"

    # ---------------------------------------------------------------- ввод
    def key_down(self, name):
        if self.phase in ("countdown", "finished"):
            return
        self.down[name] = self.t
        if name in ("A", "D"):
            self.press_zone[name] = self.zone_kind()
            if self.phase == "run" and self.press_zone[name] == "S":
                direction = -1.0 if name == INWARD_KEY else 1.0
                self.w += direction * STRAIGHT_PUSH_IMPULSE * self.a.lateral_agility * (0.55 + self.power)
            if self.phase == "start":
                self._start_press(name)
        elif name == "Q":
            self._cross_step()

    def key_up(self, name):
        t0 = self.down.pop(name, None)
        if t0 is None or self.phase != "run":
            return
        if name in ("A", "D") and self.press_zone.get(name) == "S" and self.zone_kind() == "S":
            self._push(name, self.t - t0)

    # ------------------------------------------------------- старт (A/D по очереди)
    def _start_press(self, name):
        now = self.t
        if self.last_alt_key is not None and name != self.last_alt_key:
            inst = min(1.0 / max(now - self.last_alt_t, 0.08), 9.0)
            self.start_rate += (inst - self.start_rate) * 0.45
        elif self.last_alt_key == name:
            self.start_rate *= 0.65            # два раза подряд одна и та же — сбой ритма
        self.last_alt_key, self.last_alt_t = name, now

    # ------------------------------------------------------------- толчок на прямой
    def _push(self, name, th):
        a = self.a
        interval = self.t - self.last_push_t
        q_hold = (1 - math.exp(-th / 0.14)) * (1.0 if th <= 0.55 else max(0.25, 1 - (th - 0.55) / 0.9))
        q_alt = 1.0 if name == self.next_push_key else 0.4
        q_int = smoothstep((interval - 0.30) / (0.75 - 0.30))
        q = q_hold * q_alt * q_int
        base_dv = a.push_gain * self.power * q_hold * q_int * (0.25 + 0.75 * self.headroom())
        dv = base_dv * q_alt
        self.v += dv
        self.stamina -= PUSH_STAMINA_SCALE * a.push_cost * self.power ** 2 * (0.4 + 0.6 * q_hold)
        if q < 0.6:
            miss = 1.0 - q / 0.6
            self.v = max(self.v - ACTION_MISS_SPEED_COST * miss, 0.0)
            self.stamina -= ACTION_MISS_STAMINA_COST * miss
        self.pushes += 1
        if q > 0.6:
            self.good_pushes += 1
            self.say("ТОЛЧОК %d%%" % round(q * 100), (110, 220, 130), 0.9)
        elif q_alt < 1:
            self.say("Сейчас нужен толчок %s" % self.next_push_key, (255, 150, 90), 1.0)
        elif q_int < 0.6:
            self.say("Не частите — толчки слипаются", (255, 150, 90), 1.0)
        elif th < 0.25:
            self.say("Держи кнопку дольше (~0.5 с)", (255, 200, 90), 1.0)
        else:
            self.say("Слабый толчок %d%%" % round(q * 100), (255, 200, 90), 0.9)
        self.last_push_key, self.last_push_t = name, self.t
        self.last_push_dv = dv
        self.last_push_q_alt = q_alt
        if q_alt == 1.0:
            self.next_push_key = "D" if name == "A" else "A"

    # ---------------------------------------------------------- скрестный шаг (Q)
    def _cross_step(self):
        if self.phase != "run":
            return
        a = self.a
        if self.zone_kind() != "C":
            self.stamina -= 0.5
            self.say("Q работает только в повороте", (255, 150, 90), 1.0)
            return
        now = self.t
        interval = None if self.last_q_t is None else now - self.last_q_t
        self.last_q_t = now
        self.last_q_interval = interval
        self.steps += 1
        if interval is None or interval > 1.3:
            g = 0.55
            self.say("Первый шаг", (200, 220, 255), 0.7)
        elif interval < 0.30:
            g = 0.0
            self.v -= 0.12
            self.stamina -= CROSS_STEP_MISS_COST
            self.say("СЛИШКОМ ЧАСТО — сбой шага!", (255, 110, 90), 1.0)
        else:
            g = math.exp(-((interval - a.cross_opt) / a.cross_tol) ** 2)
            if g > 0.6:
                self.good_steps += 1
                self.say("ШАГ %.2f с  ✓" % interval, (110, 220, 130), 0.7)
            elif interval < a.cross_opt:
                self.say("Шаг %.2f с — частовато" % interval, (255, 200, 90), 0.8)
            else:
                self.say("Шаг %.2f с — редковато" % interval, (255, 200, 90), 0.8)
        if interval is not None and g < 0.6:
            miss = 1.0 - g / 0.6
            self.v = max(self.v - ACTION_MISS_SPEED_COST * miss, 0.0)
            self.stamina -= ACTION_MISS_STAMINA_COST * miss
        self.v += a.cross_gain * g * (0.25 + 0.75 * self.headroom())
        self.stamina -= CROSS_STEP_STAMINA_COST

    # ------------------------------------------------------------- шаг симуляции
    def update(self, dt, draft_strength=0.0):
        if self.fb_t > 0:
            self.fb_t -= dt
        if self.phase == "countdown":
            self.cd -= dt
            if self.cd <= 0:
                self.phase = "start"
                self.say("СТАРТ!", (255, 196, 66), 1.0)
            return
        if self.phase == "finished":
            self.v *= math.exp(-0.45 * dt)
            self.s += self.v * dt
            self.u += (3.0 - self.u) * 0.6 * dt
            return

        self.t += dt
        if self.crash_cd > 0:
            self.crash_cd -= dt
        a = self.a
        boost_accel, _, boost_triggered = self.draft_slingshot.update(
            dt, draft_strength, enabled=self.phase == "run"
        )

        # --- сила толчков (W / S)
        if "W" in self.down:
            self.power += 0.55 * dt
        if "S" in self.down:
            self.power -= 0.55 * dt
        self.power = clamp(self.power, 0.2, 1.0)

        kind, _ = zone_of(self.track_s)
        curve = kind == "C"
        if self.phase == "start":
            # A/D остаются для стартового ритма; линию отдельно задают стрелки.
            inward = "LEFT" in self.down
            outward = "RIGHT" in self.down
        else:
            inward = INWARD_KEY in self.down
            outward = OUTWARD_KEY in self.down

        # --- боковое движение: A/D + снос в повороте
        lat = a.lateral_agility * LAT_ACC * (0.5 + 0.5 * self.power) * (0.8 if curve else 1.0)
        acc = 0.0
        if inward:
            acc -= lat
        if outward:
            acc += lat
        if curve:
            # центростремительная потребность v^2 / r: чем ближе к центру (меньше r) — тем сильнее снос
            r = CURVE_R + self.u
            drift = (1.0 - a.edge_grip) * self.v ** 2 / r
            if inward:
                drift *= 0.6          # A: меньше выносит
            if outward:
                drift *= 1.3          # D: сильнее выносит
            acc += drift
            damp = 1.0                # в повороте поправить траекторию трудно
        else:
            # На прямой во время обычного забега нажатие A/D даёт импульс.
            # На старте стрелки плавно смещают игрока независимо от ритма A/D.
            if self.phase == "start":
                self.w += acc * dt
            self.w *= math.exp(-STRAIGHT_DRAG * dt)
        if curve:
            self.w += (acc - damp * self.w) * dt
        self.u += self.w * dt

        # --- границы: фишки и маты
        if self.u < U_BLOCKS:
            self.u = U_BLOCKS
            self.w = max(self.w, 0.0)
            if curve:
                self.v = max(self.v - 0.6 * dt, 0.0)     # зацепил фишки
        mat_edge = mats_limit(self.track_s)
        if self.u >= mat_edge:
            self.u = mat_edge
            self.w = -0.6
            if self.crash_cd <= 0:
                self.crash_cd = 1.0
                self.crashes += 1
                self.v *= 0.62
                self.stamina -= 8.0
                self.say("УДАР О МАТЫ!", (255, 90, 80), 1.4)

        # --- скорость
        if self.phase == "start":
            idle = self.t - self.last_alt_t
            if idle > 0.30:
                self.start_rate = max(0.0, self.start_rate - 14.0 * dt)
            self.start_pow = clamp(self.start_rate / START_RATE_FULL, 0.0, 1.0)
            self.v += START_ACC * self.start_pow * a.start_power * dt
            self.v = min(self.v, self.v_cap())
            self.stamina -= START_STAMINA_DRAIN * self.start_pow * dt
            if self.t >= START_TIME:
                self.phase = "run"
                # A/D presses started during the start must not become straight pushes
                # when the player releases them after the phase changes.
                for name in ("A", "D"):
                    self.down.pop(name, None)
                    self.press_zone.pop(name, None)
                self.say("Чередуй толчки A → D; перед поворотом закончи на D", (200, 220, 255), 2.2)
        else:
            draft_drag = 1.0 - DRAFT_SPEED_DRAG_REDUCTION * clamp(
                draft_strength, 0.0, 1.0
            )
            lam = a.glide * (0.45 if curve else 1.0) * draft_drag
            self.v -= lam * (self.v - a.v_floor) * dt                  # затухание
            cap = self.v_cap()
            if self.v > cap:
                self.v -= 0.9 * (self.v - cap) * dt                    # усталость давит потолок
            if curve:
                if inward:
                    self.v -= 0.25 * dt                                # A: немного теряем скорость
                if outward:
                    self.v += 0.30 * self.power * (0.25 + 0.75 * self.headroom()) * dt   # D: чуть добавляем
                if inward or outward:
                    self.stamina -= CURVE_CONTROL_STAMINA_DRAIN * self.power * dt
            self.v += boost_accel * dt
            if boost_triggered:
                self.stamina -= DRAFT_BOOST_STAMINA_COST
            air_drain = BASE_STAMINA_DRAIN * (self.v / 12.0) ** 2
            self.stamina -= air_drain * (1.0 - DRAFT_MAX_SAVING * clamp(draft_strength, 0.0, 1.0)) * dt
        self.stamina = clamp(self.stamina + a.stamina_regen * dt, 0.0, a.stamina_max)
        if boost_triggered:
            self.say("РЫВОК ИЗ АЭРОМЕШКА", (110, 220, 245), DRAFT_BOOST_DURATION)
        if self.stamina <= 0.0 and not self.exhausted:
            self.exhausted = True
            self.say("СИЛ НЕТ! Скорость падает до базовой", (255, 90, 80), 2.0)
        if self.stamina > 0.15 * a.stamina_max:
            self.exhausted = False
        self.v = max(self.v, 0.0)

        # --- путь вдоль линии замера (внешняя линия в повороте длиннее)
        scale = (CURVE_R + self.u) / CURVE_R if curve else 1.0
        ds = self.v * dt / scale
        self.s += ds

        # --- круги и отрезки
        lap = int(self.s // LAP_LEN)
        if lap > self.lap_idx:
            self.laps.append(self.t - self.lap_t0)
            self.lap_t0 = self.t
            self.lap_idx = lap
        kind, zi = zone_of(self.track_s)
        if zi != self.cur_zone:
            if kind == "C":
                if self.last_push_key != "D":
                    self.say("Перед поворотом последний толчок должен быть D", (255, 150, 90), 1.2)
                    if self.last_push_key is not None and self.last_push_q_alt == 1.0:
                        self.v = max(self.v - 0.6 * self.last_push_dv, 0.0)
                # Each straight gets a fresh push sequence; no alternation carries through a turn.
                self.last_push_key = None
                self.last_push_t = -9.0
                self.next_push_key = "A"
                self.last_push_dv = 0.0
                self.last_push_q_alt = 1.0
            self.sectors.append((SECTOR_NAMES[self.cur_zone], self.t - self.sector_t0))
            self.sector_t0 = self.t
            self.cur_zone = zi

        # --- след и лог скорости
        self._trail_t += dt
        if self._trail_t >= 0.04:
            self._trail_t = 0.0
            x, y, _ = track_pos(self.track_s, self.u)
            self.trail.append((x, y))
            self.speed_log.append(self.v)

        # --- финиш
        if self.s >= self.distance:
            over = self.s - self.distance
            self.finish_time = self.t - (over / ds) * dt if ds > 1e-9 else self.t
            self.phase = "finished"
            self.down.clear()
            self.say("ФИНИШ!", (255, 196, 66), 3.0)
