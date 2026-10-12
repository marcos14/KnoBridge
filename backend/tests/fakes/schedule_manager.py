"""In-memory ``ScheduleManager``: what the API and reconciliation tests use instead of Temporal."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from knobridge.ingestion.errors import ScheduleUnavailableError
from knobridge.ingestion.schedule import ScheduleChange, SourceSchedule


@dataclass
class FakeScheduleManager:
    """Keeps the schedules by source in ``schedules`` and every call in ``calls`` (``("apply",
    source_id)`` or ``("remove", source_id)``); ``unavailable = True`` makes every call fail as
    if Temporal were down."""

    schedules: dict[uuid.UUID, SourceSchedule] = field(
        default_factory=lambda: dict[uuid.UUID, SourceSchedule]()
    )
    calls: list[tuple[str, uuid.UUID]] = field(default_factory=lambda: [])
    unavailable: bool = False

    async def apply(self, schedule: SourceSchedule) -> ScheduleChange:
        self._check_available()
        self.calls.append(("apply", schedule.source_id))
        current = self.schedules.get(schedule.source_id)
        self.schedules[schedule.source_id] = schedule
        if current is None:
            return ScheduleChange.CREATED
        return ScheduleChange.UNCHANGED if current == schedule else ScheduleChange.UPDATED

    async def remove(self, source_id: uuid.UUID) -> bool:
        self._check_available()
        self.calls.append(("remove", source_id))
        return self.schedules.pop(source_id, None) is not None

    async def scheduled_sources(self) -> set[uuid.UUID]:
        self._check_available()
        return set(self.schedules)

    def _check_available(self) -> None:
        if self.unavailable:
            raise ScheduleUnavailableError("temporal is down")
