"""Small dependency container shared by API routers."""

from .core.config import get_settings
from .services.analysis import AnalysisService
from .services.storage import StorageService
from .services.tasks import TaskStore

settings = get_settings()
storage = StorageService(settings)
tasks = TaskStore(ttl_seconds=settings.task_ttl_seconds)
analysis = AnalysisService(storage, tasks)

