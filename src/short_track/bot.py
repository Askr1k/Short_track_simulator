"""В модуле описываются действия бота, который показывает
мировой рекорд на текушей дистанции"""
import math

from .config import LAP_LEN, SEG_B, U_BLOCKS, WORLD_RECORDS
from .track import zone_of
from .utils import clamp


class RecordBot:
    """В классе описывается сам бот и функции его движения и отображения"""

    def __init__(self, distance, athlete):
        self.distance = distance
        self.athlete = athlete
        self.s = 0.0
        self.v = 0.0
        self.u = 0.25
        self.w = 0.0
        self.accel_time = 3.0
        record_time = WORLD_RECORDS[distance]
        self.peak_time = record_time * 0.55
        self.start_speed_factor = 0.95
        self.peak_speed_factor = 1.05
        self.finish_speed_factor = 1.00
        profile_area = (
            self.accel_time * self.start_speed_factor / 2
            + (self.peak_time - self.accel_time)
            * (self.start_speed_factor + self.peak_speed_factor) / 2
            + (record_time - self.peak_time)
            * (self.peak_speed_factor + self.finish_speed_factor) / 2
        )
        self.profile_mean = profile_area / record_time
        self.action = "ГОТОВ"
        self.action_until = 0.0
        self.next_action = 0.0
        self.last_zone = -1
        self.push_key = "A"
        self.pushing = False

    def update(self, dt, race):
        if race.phase == "countdown":
            self.action = "ГОТОВ"
            return

        clock = race.t
        previous_v = self.v
        self.v = self._speed_at(clock)
        self.s = min(
            self.distance,
            self.s + (previous_v + self.v) * 0.5 * dt,
        )
        if clock >= WORLD_RECORDS[self.distance]:
            self.s = self.distance
        if race.phase == "start":
            self.action = "СТАРТ A" if int(
                clock / 0.18) % 2 == 0 else "СТАРТ D"
            target_u = 0.15
            zone_index = -2
        else:
            kind, zone_index = zone_of(self.s)
            target_u = -0.32 if kind == "C" else 0.18
            if zone_index != self.last_zone:
                self.next_action = clock + \
                    (self.athlete.cross_opt if kind == "C" else 0.0)
                self.pushing = False
                self.push_key = "A"

            if kind == "C":
                if clock >= self.next_action:
                    self.action = "Q · ШАГ"
                    self.action_until = clock + 0.16
                    self.next_action = clock + self.athlete.cross_opt
                elif clock < self.action_until:
                    self.action = "Q · ШАГ"
                else:
                    self.action = "РУЛИТ A" if self.u > target_u + 0.04 else "ДУГА"
            elif clock >= self.next_action:
                key = self.push_key
                remaining = SEG_B[zone_index] - (self.s % LAP_LEN)
                time_to_turn = remaining / max(self.v, 0.1)
                if key == "A":
                    if time_to_turn < 0.8:
                        self.action = "ГЛАЙД"
                        self.pushing = False
                        self.next_action = clock + 0.75
                    else:
                        self.action = "ТОЛЧОК A"
                        self.action_until = clock + 0.50
                        self.next_action = clock + 0.75
                        self.push_key = "D"
                        self.pushing = True
                else:
                    self.action = "ТОЛЧОК D"
                    self.action_until = clock + 0.50
                    self.next_action = clock + 0.75
                    self.push_key = "A"
                    self.pushing = True
            elif clock < self.action_until and self.pushing:
                self.action = "ТОЛЧОК " + \
                    ("A" if self.push_key == "D" else "D")
            else:
                self.pushing = False
                self.action = "РУЛИТ D" if self.u < target_u - 0.04 else "ГЛАЙД"

        desired_w = clamp((target_u - self.u) * 2.2, -1.5, 1.5)
        self.w += (desired_w - self.w) * (1.0 - math.exp(-4.0 * dt))
        self.u = clamp(self.u + self.w * dt, U_BLOCKS + 0.05, 2.0)
        self.last_zone = zone_index

    def _speed_at(self, clock):
        """Smooth start, mid-race peak, and a small late-race fade."""
        record_time = WORLD_RECORDS[self.distance]
        if clock < self.accel_time:
            factor = self.start_speed_factor * \
                self._smoothstep(clock / self.accel_time)
        elif clock < self.peak_time:
            progress = (clock - self.accel_time) / \
                (self.peak_time - self.accel_time)
            factor = self.start_speed_factor + (
                self.peak_speed_factor - self.start_speed_factor
            ) * self._smoothstep(progress)
        else:
            progress = (clock - self.peak_time) / \
                (record_time - self.peak_time)
            factor = self.peak_speed_factor + (
                self.finish_speed_factor - self.peak_speed_factor
            ) * self._smoothstep(progress)
        return (self.distance / record_time) * factor / self.profile_mean

    @staticmethod
    def _smoothstep(value):
        x = clamp(value, 0.0, 1.0)
        return x * x * (3.0 - 2.0 * x)
