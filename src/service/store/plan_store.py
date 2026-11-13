"""The Pianificatore's plans of the activities (Postgres)."""
from sqlalchemy.engine import Engine

from domain.store.db.mapper import as_utc
from domain.store.db.plan_repository import DbActivityPlanRepository
from models.domain.plan import ActivityPlan
from models.store.db import ActivityPlanTable


def _plan(row: ActivityPlanTable) -> ActivityPlan:
    plan = ActivityPlan.model_validate(row.model_dump())
    plan.created_at, plan.updated_at = as_utc(plan.created_at), as_utc(plan.updated_at)
    return plan


class PlanStore:

    def __init__(self, engine: Engine):
        self._plans = DbActivityPlanRepository(engine)

    def save(self, plan: ActivityPlan) -> ActivityPlan:
        """New or updated (by ``id``)."""
        return _plan(self._plans.save(ActivityPlanTable(**plan.model_dump(mode="json", exclude={"created_at", "updated_at"}),
                                                        created_at=plan.created_at, updated_at=plan.updated_at)))

    def latest(self, project_name: str, activity: str) -> ActivityPlan | None:
        """The activity's latest plan, whatever its status."""
        row = self._plans.latest(project_name, activity)
        return _plan(row) if row else None

    def latest_per_activity(self, project_name: str) -> list[ActivityPlan]:
        """The latest plan of each activity of the project."""
        seen: set[str] = set()
        plans = []
        for row in self._plans.list_for_project(project_name):
            if row.activity not in seen:
                seen.add(row.activity)
                plans.append(_plan(row))
        return plans
