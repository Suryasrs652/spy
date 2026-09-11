"""Import every module's models so Base.metadata is fully populated.

Alembic's env.py imports this module (and nothing else) to discover the
target schema for autogenerate/upgrade. Add new model modules here.
"""
from app.modules.admin import models as admin_models  # noqa: F401
from app.modules.audits import models as audits_models  # noqa: F401
from app.modules.auth import models as auth_models  # noqa: F401
from app.modules.backlinks import models as backlinks_models  # noqa: F401
from app.modules.competitors import models as competitors_models  # noqa: F401
from app.modules.crawler import models as crawler_models  # noqa: F401
from app.modules.gsc import models as gsc_models  # noqa: F401
from app.modules.keywords import models as keywords_models  # noqa: F401
from app.modules.notifications import models as notifications_models  # noqa: F401
from app.modules.organizations import models as organizations_models  # noqa: F401
from app.modules.projects import models as projects_models  # noqa: F401
from app.modules.recommendations import models as recommendations_models  # noqa: F401
from app.modules.reports import models as reports_models  # noqa: F401
from app.modules.seo import models as seo_models  # noqa: F401

from app.db.base import Base  # noqa: E402,F401 (re-exported for env.py)
