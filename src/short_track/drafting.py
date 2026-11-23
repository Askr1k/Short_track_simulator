"""Общий механизм накопления аэромешка и рывка при выходе из него."""

from .config import (
    DRAFT_BOOST_ACCEL, DRAFT_BOOST_BUILD_TIME, DRAFT_BOOST_COOLDOWN,
    DRAFT_BOOST_DURATION, DRAFT_BOOST_EXIT_STRENGTH,
    DRAFT_BOOST_MIN_STRENGTH,
)


class DraftSlingshot:
    """Награждает коротким ускорением за выход из устойчивого аэромешка."""

    def __init__(self):
        self.draft_time = 0.0
        self.in_draft = False
        self.boost_time = 0.0
        self.cooldown = 0.0

    def update(self, dt, strength, enabled=True):
        """Возвращает ускорение, силу активного рывка и флаг его запуска."""
        self.cooldown = max(0.0, self.cooldown - dt)
        if not enabled:
            self.draft_time = 0.0
            self.in_draft = False
            return 0.0, 0.0, False

        triggered = False
        if self.in_draft:
            if strength < DRAFT_BOOST_EXIT_STRENGTH:
                if (self.draft_time >= DRAFT_BOOST_BUILD_TIME
                        and self.cooldown <= 0.0):
                    self.boost_time = DRAFT_BOOST_DURATION
                    self.cooldown = DRAFT_BOOST_COOLDOWN
                    triggered = True
                self.draft_time = 0.0
                self.in_draft = False
        elif strength >= DRAFT_BOOST_MIN_STRENGTH:
            self.draft_time += dt
            if self.draft_time >= DRAFT_BOOST_BUILD_TIME:
                self.in_draft = True
        else:
            self.draft_time = 0.0

        factor = min(1.0, self.boost_time / DRAFT_BOOST_DURATION)
        acceleration = DRAFT_BOOST_ACCEL * factor
        self.boost_time = max(0.0, self.boost_time - dt)
        return acceleration, factor, triggered
