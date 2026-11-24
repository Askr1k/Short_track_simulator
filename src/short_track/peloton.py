"""Соперники, тактика пелотона, аэромешок и контактная борьба."""
from dataclasses import dataclass, replace
import math
import random

from .athletes import ROSTER
from .config import (
    BASE_STAMINA_DRAIN, CURVE_R, CROSS_STEP_STAMINA_COST,
    DRAFT_BOOST_DURATION, DRAFT_BOOST_STAMINA_COST, DRAFT_FULL_DISTANCE,
    DRAFT_LATERAL_OFFSET, DRAFT_LATERAL_RANGE, DRAFT_MAX_DISTANCE,
    DRAFT_MAX_SAVING, DRAFT_SPEED_DRAG_REDUCTION, INWARD_KEY, LAP_LEN, MAX_SPEED_SCALE,
    NPC_ACTION_SCALE, NPC_PACK_LANE_MAX, NPC_PASS_LANE_MAX,
    NPC_REGEN_SCALE, NPC_SPEED_SCALE,
    PUSH_STAMINA_SCALE, RACE_OPPONENT_COUNTS, SEG_B, START_ACC,
    START_STAMINA_DRAIN, STRAIGHT_PUSH_IMPULSE,
    STAMINA_CAP_EXP, U_BLOCKS, U_MATS,
)
from .track import mats_limit, track_pos, zone_of
from .drafting import DraftSlingshot
from .utils import clamp, smoothstep


@dataclass(frozen=True)
class Personality:
    """Тактический профиль соперника."""

    name: str
    early_power: float
    middle_power: float
    late_power: float
    attack_fraction: float
    aggression: float
    drafting: float


PERSONALITIES = (
    Personality("Ранний лидер", 0.98, 0.91, 0.82, 0.16, 0.88, 0.20),
    Personality("Финишёр", 0.62, 0.73, 1.00, 0.78, 0.62, 0.82),
    Personality("Ровный темп", 0.82, 0.84, 0.88, 0.50, 0.45, 0.62),
    Personality("Обгонщик", 0.87, 0.94, 0.98, 0.40, 1.00, 0.35),
    Personality("Экономный", 0.67, 0.77, 0.98, 0.80, 0.28, 1.00),
)


class Opponent:
    """Самостоятельный конькобежец с физикой и выбранным стилем гонки."""

    def __init__(self, number, distance, athlete, role, personality, start_offset, lane):
        self.number = number
        self.distance = distance
        self.athlete = athlete
        self.role = role
        self.personality = personality
        self.prefers_outer_pass = role == "Спринтер" or random.random() < 0.25
        self.name = "%s %d" % (athlete.name, number)
        self.start_offset = start_offset
        self.progress = 0.0
        self.s = start_offset
        self.u = lane
        self.w = 0.0
        self.v = 0.0
        self.stamina = athlete.stamina_max
        self.draft_slingshot = DraftSlingshot()
        self.slingshot_until = 0.0
        self.power = 0.8
        self.skill = random.uniform(1.0, 1.04)
        self.chase_bonus = 0.0
        self.yielding = False
        self.finished = False
        self.finish_time = None
        self.action = "ГОТОВ"
        self.action_until = 0.0
        self.current_zone = None
        self.next_push_time = 0.0
        self.next_step_time = 0.0
        self.last_push_time = -1.0
        self.push_key = "A"
        self.start_key = "A"
        self.next_start_time = 0.0
        self.push_lane_bias = 0.0
        self.step_count = 0

        # На короткой дистанции почти все соперники стараются сразу занять место впереди.
        self.trait_strength = 0.15 + 0.85 * ((distance - 500) / 1000.0)
        self.trait_strength = clamp(self.trait_strength, 0.15, 1.0)

    def speed_cap(self):
        a = self.athlete
        stamina_ratio = clamp(self.stamina / a.stamina_max, 0.0, 1.0)
        max_speed = a.v_max * MAX_SPEED_SCALE
        return a.v_floor + (max_speed - a.v_floor) * stamina_ratio ** STAMINA_CAP_EXP

    def headroom(self):
        cap = self.speed_cap()
        return clamp((cap - self.v) / max(cap - self.athlete.v_floor, 0.5), 0.0, 1.0)

    def _target_power(self):
        race_length = max(self.distance - self.start_offset, 1.0)
        fraction = clamp(self.progress / race_length, 0.0, 1.0)
        if self.distance == 500:
            common_early, common_late = 0.94, 0.99
        elif self.distance == 1000:
            common_early, common_late = 0.82, 0.94
        else:
            common_early, common_late = 0.72, 0.91
        common = common_early + (common_late - common_early) * fraction

        if fraction < self.personality.attack_fraction:
            blend = smoothstep(fraction / self.personality.attack_fraction)
            personal = self.personality.early_power + (
                self.personality.middle_power - self.personality.early_power
            ) * blend
        else:
            blend = smoothstep(
                (fraction - self.personality.attack_fraction)
                / (1.0 - self.personality.attack_fraction)
            )
            personal = self.personality.middle_power + (
                self.personality.late_power - self.personality.middle_power
            ) * blend
        personality_window = {500: 0.58, 1000: 0.68, 1500: 0.74}[self.distance]
        trait_influence = self.trait_strength * smoothstep(
            fraction / personality_window
        )
        target = common * (1.0 - trait_influence) + personal * trait_influence
        if self.yielding:
            return min(target, 0.62)
        return clamp(target + self.chase_bonus + 0.025, 0.45, 1.0)

    def plan(self, field):
        """Выбирает линию и силу аэромешка по ближайшим участникам."""
        kind, _ = zone_of(self.s)
        target_u = -0.22 if kind == "C" else 0.22
        leader = max(field, key=_track_s)
        if leader is not self and _track_s(leader) - self.s >= LAP_LEN - 8.0:
            self.yielding = True
            return U_MATS - 0.65, 0.0
        self.yielding = False
        ahead = []
        for rival in field:
            if rival is self:
                continue
            gap = _track_s(rival) - self.s
            if 0.2 < gap < 12.0:
                ahead.append((gap, rival))
        ahead.sort(key=lambda item: item[0])

        player = next((rival for rival in field
                       if getattr(rival, "phase", None) is not None), None)
        defend_inner = False
        if (player is not None and player.phase == "run"
                and player.u <= 1.0 and player.v >= self.v - 0.4):
            player_s = _track_s(player)
            blockers = [
                (_track_s(rival) - player_s, rival)
                for rival in field
                if rival is not player and 0.2 < _track_s(rival) - player_s < 8.0
            ]
            if blockers:
                _, first_blocker = min(blockers, key=lambda item: item[0])
                defend_inner = first_blocker is self

        draft_leader = None
        draft_strength = 0.0
        for gap, rival in ahead:
            strength = _draft_strength(gap, self.u, rival.u)
            if strength > draft_strength:
                draft_strength = strength
                draft_leader = rival

        should_pass = False
        if ahead:
            gap, blocker = ahead[0]
            aggression = 0.68 * (1.0 - self.trait_strength) + (
                self.personality.aggression * self.trait_strength
            )
            draft_priority = 0.72 * (1.0 - self.trait_strength) + (
                self.personality.drafting * self.trait_strength
            )
            race_length = max(self.distance - self.start_offset, 1.0)
            race_fraction = clamp(self.progress / race_length, 0.0, 1.0)
            attack_from = {500: 0.58, 1000: 0.68, 1500: 0.74}[self.distance]
            runaway = self.chase_bonus >= 0.12
            # До атакующего отрезка соперники держатся за группой, если лидер не убежал.
            should_pass = (gap < 9.0 and aggression > 0.54
                           and (race_fraction >= attack_from or runaway))
            if should_pass:
                # У части соперников профиль обгона начинается с внешней дорожки.
                if self.prefers_outer_pass:
                    pass_lanes = (blocker.u + 1.1, blocker.u - 1.1, 1.05, -0.22)
                else:
                    pass_lanes = (blocker.u - 1.1, blocker.u + 1.1, -0.22, 1.05)
                tried_lanes = set()
                for lane in pass_lanes:
                    lane = round(clamp(lane, U_BLOCKS + 0.25,
                                       min(mats_limit(self.s) - 0.7,
                                           NPC_PASS_LANE_MAX)), 2)
                    if lane in tried_lanes:
                        continue
                    tried_lanes.add(lane)
                    if self._lane_is_clear(lane, field):
                        target_u = lane
                        draft_strength = 0.0
                        break
                else:
                    if draft_leader is not None:
                        target_u = draft_leader.u + DRAFT_LATERAL_OFFSET
            elif draft_priority > 0.30:
                # Даже до зоны полноценного мешка соперник заранее встаёт в линию за лидером.
                line_leader = draft_leader if draft_leader is not None else blocker
                if draft_leader is not None or gap <= DRAFT_MAX_DISTANCE + 3.0:
                    target_u = clamp(
                        line_leader.u + DRAFT_LATERAL_OFFSET,
                        U_BLOCKS + 0.08,
                        min(mats_limit(self.s) - 0.55, NPC_PACK_LANE_MAX),
                    )

        if defend_inner and not should_pass:
            # Ближайший бот закрывает внутреннюю дорожку перед игроком.
            target_u = clamp(player.u + 0.45, U_BLOCKS + 0.25, 1.1)
            draft_strength = 0.0

        target_u = clamp(target_u, U_BLOCKS + 0.08,
                         min(mats_limit(self.s) - 0.55,
                             NPC_PASS_LANE_MAX))
        return target_u, draft_strength

    def _lane_is_clear(self, lane, field):
        for rival in field:
            if rival is self:
                continue
            if abs(_track_s(rival) - self.s) < 2.2 and abs(rival.u - lane) < 0.72:
                return False
        return True

    def update(self, dt, race, target_u, draft_strength, clock):
        """Обновляет разгон, действия, усталость и положение соперника."""
        if race.phase == "countdown" or self.finished:
            return

        a = self.athlete
        boost_accel, _, boost_triggered = self.draft_slingshot.update(
            dt, draft_strength, enabled=race.phase == "run"
        )
        if boost_triggered:
            self.stamina -= DRAFT_BOOST_STAMINA_COST
            self.slingshot_until = clock + DRAFT_BOOST_DURATION
        if race.phase == "start":
            # В стартовом разгоне все держат близкую мощность, роли проявятся дальше.
            target_power = {500: 0.94, 1000: 0.87, 1500: 0.80}[self.distance]
        else:
            target_power = self._target_power()
        self.power += clamp(target_power - self.power, -0.45 * dt, 0.45 * dt)

        if race.phase == "start":
            if clock >= self.next_start_time:
                self.action = "СТАРТ " + self.start_key
                self.start_key = "D" if self.start_key == "A" else "A"
                self.next_start_time = clock + 1.0 / 6.5
            self.v += START_ACC * a.start_power * self.power * dt
            self.v = min(self.v, self.speed_cap())
            self.stamina -= START_STAMINA_DRAIN * self.power * dt
        else:
            kind, zone_index = zone_of(self.s)
            if zone_index != self.current_zone:
                self.current_zone = zone_index
                self.action_until = clock
                if kind == "S":
                    self.push_key = "A"
                    self.next_push_time = clock + 0.12
                else:
                    self.next_step_time = clock + a.cross_opt

            if kind == "S":
                if clock >= self.action_until:
                    self.action = "ГЛАЙД"
                remaining = _distance_to_sector_end(self.s, zone_index)
                time_to_turn = remaining / max(self.v, 8.0)
                if clock >= self.next_push_time:
                    if self.push_key == "A" and time_to_turn < 0.9:
                        self.push_key = "D"
                        self.next_push_time = clock + 0.12
                    elif self.push_key == "D" and time_to_turn < 0.35:
                        self.next_push_time = clock + 0.12
                    else:
                        self._push(clock)
                        self.next_push_time = clock + 0.74
            else:
                if clock >= self.next_step_time:
                    self._cross_step(clock)
                    self.next_step_time = clock + a.cross_opt
                elif clock >= self.action_until:
                    self.action = "ДУГА"

            draft_drag = 1.0 - DRAFT_SPEED_DRAG_REDUCTION * clamp(
                draft_strength, 0.0, 1.0
            )
            self.v -= a.glide * (self.v - a.v_floor) * draft_drag * dt
            cap = self.speed_cap()
            if self.v > cap:
                self.v -= 0.9 * (self.v - cap) * dt
            if kind == "C":
                self.v = max(self.v - 0.08 * dt, 0.0)
            self.v += boost_accel * dt

            air_drain = BASE_STAMINA_DRAIN * (self.v / 12.0) ** 2
            self.stamina -= air_drain * (1.0 - DRAFT_MAX_SAVING * draft_strength) * dt

        self.stamina = clamp(self.stamina + a.stamina_regen * dt, 0.0, a.stamina_max)
        self._steer(dt, target_u, kind="C" if race.phase != "start"
                    and zone_of(self.s)[0] == "C" else "S")
        if clock < self.slingshot_until:
            self.action = "РЫВОК ИЗ МЕШКА"

        zone = zone_of(self.s)[0]
        scale = (CURVE_R + self.u) / CURVE_R if zone == "C" else 1.0
        ds = self.v * dt / max(scale, 0.2)
        self.progress += ds
        self.s += ds
        if self.s >= self.distance:
            over = self.s - self.distance
            self.s = self.distance
            self.progress = self.distance - self.start_offset
            self.finish_time = clock - (over / ds) * dt if ds > 1e-9 else clock
            self.finished = True
            self.action = "ФИНИШ"

    def _push(self, clock):
        a = self.athlete
        q = self.skill * (0.75 + 0.25 * self.headroom())
        self.v += a.push_gain * self.power * q
        self.stamina -= PUSH_STAMINA_SCALE * a.push_cost * self.power ** 2
        inward = self.push_key == "A"
        direction = -1.0 if self.push_key == INWARD_KEY else 1.0
        # Толчок на прямой одновременно смещает бота, как нажатие A/D у игрока.
        lateral_impulse = STRAIGHT_PUSH_IMPULSE * a.lateral_agility * (0.55 + self.power)
        self.w += direction * lateral_impulse
        self.push_lane_bias = -0.25 if inward else 0.25
        self.action = "ТОЛЧОК " + self.push_key
        self.action_until = clock + 0.24
        self.push_key = "D" if self.push_key == "A" else "A"
        self.last_push_time = clock

    def _cross_step(self, clock):
        a = self.athlete
        self.v += a.cross_gain * self.skill * (0.25 + 0.75 * self.headroom())
        self.stamina -= CROSS_STEP_STAMINA_COST
        self.action = "Q · ШАГ"
        self.action_until = clock + 0.16
        self.step_count += 1

    def _steer(self, dt, target_u, kind):
        if kind == "S":
            self.push_lane_bias *= math.exp(-2.0 * dt)
        steer_limit = mats_limit(self.s) - 0.55
        if not self.yielding:
            steer_limit = min(steer_limit, NPC_PASS_LANE_MAX)
        target_u = clamp(target_u + self.push_lane_bias,
                         U_BLOCKS + 0.08, steer_limit)
        if kind == "C":
            radius = CURVE_R + self.u
            drift = (1.0 - self.athlete.edge_grip) * self.v ** 2 / max(radius, 1.0)
        else:
            drift = 0.0
        desired_w = clamp((target_u - self.u) * 2.2 - drift, -2.2, 2.2)
        self.w += (desired_w + drift - self.w) * (1.0 - math.exp(-4.0 * dt))
        outer_limit = mats_limit(self.s) - 0.3
        if not self.yielding:
            outer_limit = min(outer_limit, NPC_PASS_LANE_MAX)
        self.u = clamp(self.u + self.w * dt, U_BLOCKS + 0.05, outer_limit)


class Peloton:
    """Создаёт группу соперников и управляет обгонами, мешком и контактами."""

    def __init__(self, distance, player_athlete):
        self.distance = distance
        self.opponents = []
        self.contact_cooldowns = {}
        self.clock = 0.0
        self.last_race_time = 0.0
        count = RACE_OPPONENT_COUNTS[distance]
        slots = [
            (0.0, 0.20), (0.0, 1.65), (0.0, 3.10), (0.0, 4.55),
            (-1.25, 0.90), (-1.25, 2.35), (-1.25, 3.80), (-1.25, 5.25),
        ]
        random.shuffle(slots)
        self.player_start_offset, self.player_start_lane = slots.pop()
        athlete_pool = [athlete for athlete in ROSTER if athlete != player_athlete]
        if not athlete_pool:
            athlete_pool = ROSTER
        roles = ["Спринтер", "Стайер", "Универсал"]
        random.shuffle(roles)
        for index in range(count):
            template = random.choice(athlete_pool)
            role = roles[index % len(roles)]
            athlete = _balanced_athlete(template, role)
            personality = random.choice(PERSONALITIES)
            start_offset, lane = slots.pop()
            self.opponents.append(Opponent(index + 1, distance, athlete, role,
                                           personality, start_offset, lane))

    def participants(self, race):
        return [race] + self.opponents

    def update(self, dt, race):
        if race.phase == "countdown":
            return
        elapsed = max(0.0, race.t - self.last_race_time)
        if elapsed > 0.0:
            self.clock += elapsed
        elif race.phase == "finished":
            self.clock += dt
        self.last_race_time = race.t
        field = self.participants(race)
        leader = max(field, key=_track_s)
        for opponent in self.opponents:
            gap_to_leader = max(0.0, _track_s(leader) - opponent.s)
            opponent.chase_bonus = clamp((gap_to_leader - 3.0) / 18.0, 0.0, 1.0) * 0.16
            target_u, draft = opponent.plan(field)
            opponent.update(dt, race, target_u, draft, self.clock)

    def player_draft_strength(self, race):
        best = 0.0
        for opponent in self.opponents:
            best = max(best, _draft_strength(opponent.s - race.track_s,
                                             race.u, opponent.u))
        return best

    def player_draft_saving_percent(self, race):
        return round(100 * DRAFT_MAX_SAVING * self.player_draft_strength(race))

    def player_place(self, race):
        player_s = race.track_s
        return 1 + sum(opponent.s > player_s for opponent in self.opponents)

    @property
    def all_finished(self):
        return all(opponent.finished for opponent in self.opponents)

    def resolve_contacts(self, race):
        """Смягчает пересечения тел и не даёт пройти прямо сквозь соперника."""
        participants = self.participants(race)
        for key in tuple(self.contact_cooldowns):
            self.contact_cooldowns[key] -= 1.0 / 120.0
            if self.contact_cooldowns[key] <= 0.0:
                del self.contact_cooldowns[key]

        for index, first in enumerate(participants):
            for second in participants[index + 1:]:
                if _is_finished(first) or _is_finished(second):
                    continue
                key = tuple(sorted((id(first), id(second))))
                first_s, second_s = _track_s(first), _track_s(second)
                x1, y1, _ = track_pos(first_s, first.u)
                x2, y2, _ = track_pos(second_s, second.u)
                if math.hypot(x2 - x1, y2 - y1) >= 1.0:
                    continue
                if key in self.contact_cooldowns:
                    continue

                if ((getattr(first, "yielding", False)
                     and (second is race or second_s > first_s))
                    or (getattr(second, "yielding", False)
                        and (first is race or first_s > second_s))):
                    continue

                raw_gap = second_s - first_s
                if abs(raw_gap) > LAP_LEN / 2:
                    gap = ((raw_gap + LAP_LEN / 2) % LAP_LEN) - LAP_LEN / 2
                else:
                    gap = raw_gap
                lateral_gap = abs(second.u - first.u)
                side_contact = (abs(gap) < 0.25
                                or (abs(gap) < 0.55 and lateral_gap >= 0.35))

                if side_contact:
                    first.v = max(0.0, first.v - 0.08)
                    second.v = max(0.0, second.v - 0.08)
                    side = 1.0 if first.u <= second.u else -1.0
                    first.w -= side * 0.08
                    second.w += side * 0.08
                    for skater in (first, second):
                        if skater is race:
                            race.stamina = max(0.0, race.stamina - 0.05)
                            race.say("ЛЁГКИЙ КОНТАКТ СБОКУ", (255, 195, 120), 0.7)
                        elif hasattr(skater, "stamina"):
                            skater.stamina = max(0.0, skater.stamina - 0.05)
                else:
                    rear, front = (first, second) if gap > 0 else (second, first)
                    rear.v = min(rear.v, max(0.0, front.v - 0.15))
                    if abs(raw_gap) < LAP_LEN / 2 and _track_s(front) - _track_s(rear) < 1.0:
                        _set_position_s(rear, _track_s(front) - 1.0)
                    rear.w += (1.0 if rear.u <= front.u else -1.0) * 0.12
                    if rear is race:
                        race.stamina = max(0.0, race.stamina - 0.2)
                        race.say("КОНТАКТ СЗАДИ", (255, 175, 90), 0.9)
                    elif hasattr(rear, "stamina"):
                        rear.stamina = max(0.0, rear.stamina - 0.2)
                self.contact_cooldowns[key] = 0.45


def _is_finished(skater):
    """Проверяет финиш NPC и игрока."""
    return getattr(skater, "finished", False) or getattr(skater, "phase", None) == "finished"


def _set_position_s(skater, value):
    """Сдвигает отстающего после контакта, сохраняя его пройденную дистанцию."""
    if hasattr(skater, "start_offset"):
        skater.s = max(skater.start_offset, value)
        skater.progress = skater.s - skater.start_offset
    else:
        skater.s = max(0.0, value - skater.track_offset)


def _track_s(skater):
    """Возвращает положение по овалу с учётом случайного стартового места."""
    return getattr(skater, "track_s", skater.s)


def _balanced_athlete(template, role):
    """Сохраняет имя и цвет шаблона, но даёт всем NPC сопоставимый уровень."""
    profiles = {
        "Спринтер": dict(v_max=15.70, stamina_max=94, stamina_regen=0.16,
                          push_gain=0.94, push_cost=1.22, start_power=1.02,
                          cross_gain=0.44, cross_opt=0.54, cross_tol=0.17,
                          edge_grip=0.89, lateral_agility=1.03, glide=0.026),
        "Стайер": dict(v_max=15.45, stamina_max=110, stamina_regen=0.21,
                       push_gain=0.86, push_cost=1.10, start_power=0.98,
                       cross_gain=0.49, cross_opt=0.58, cross_tol=0.19,
                       edge_grip=0.90, lateral_agility=0.98, glide=0.024),
        "Универсал": dict(v_max=15.58, stamina_max=102, stamina_regen=0.18,
                          push_gain=0.90, push_cost=1.16, start_power=1.0,
                          cross_gain=0.46, cross_opt=0.56, cross_tol=0.18,
                          edge_grip=0.90, lateral_agility=1.0, glide=0.025),
    }
    stats = profiles[role].copy()
    stats["v_max"] *= NPC_SPEED_SCALE * random.uniform(0.99, 1.01)
    stats["push_gain"] *= NPC_ACTION_SCALE * random.uniform(0.985, 1.015)
    stats["cross_gain"] *= NPC_ACTION_SCALE
    stats["start_power"] *= NPC_ACTION_SCALE
    stats["stamina_regen"] *= NPC_REGEN_SCALE
    return replace(template, **stats)


def _draft_strength(gap, follower_u, leader_u):
    """Возвращает силу аэромешка от 0 до 1 с учётом расстояния и линии."""
    if gap < 0.4 or gap > DRAFT_MAX_DISTANCE:
        return 0.0
    if gap <= DRAFT_FULL_DISTANCE:
        distance_factor = 1.0
    else:
        distance_factor = (DRAFT_MAX_DISTANCE - gap) / (
            DRAFT_MAX_DISTANCE - DRAFT_FULL_DISTANCE
        )
    lateral_error = abs((follower_u - leader_u) - DRAFT_LATERAL_OFFSET)
    lateral_factor = clamp(1.0 - lateral_error / DRAFT_LATERAL_RANGE, 0.0, 1.0)
    return clamp(distance_factor * lateral_factor, 0.0, 1.0)


def _distance_to_sector_end(s, zone_index):
    """Расстояние до конца текущего сегмента трассы."""
    local_s = s % LAP_LEN
    return max(0.0, SEG_B[zone_index] - local_s)
