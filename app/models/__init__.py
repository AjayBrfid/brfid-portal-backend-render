"""Import every domain model module here so its tables register on Base.metadata before Alembic
autogenerate runs — SQLAlchemy only knows about a table once its model class has been imported.
alembic/env.py imports this package (not each module individually) to trigger all of them at
once. A new model file that isn't imported here will be silently ignored by autogenerate.

Populated incrementally as each domain is built (Phase 2: user/notification; Phase 3: core-ops;
Phase 4: vendor/procurement) — intentionally empty at scaffold time.
"""
import app.models.user  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.audit  # noqa: F401
import app.models.warehouse  # noqa: F401
import app.models.catalog  # noqa: F401
import app.models.retail  # noqa: F401
import app.models.fulfillment  # noqa: F401
import app.models.vendor  # noqa: F401
import app.models.procurement  # noqa: F401
import app.models.shipping  # noqa: F401
import app.models.payment  # noqa: F401
import app.models.vendor_return  # noqa: F401
