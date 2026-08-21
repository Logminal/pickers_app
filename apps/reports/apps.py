from django.apps import AppConfig


class ReportsConfig(AppConfig):
    name = 'apps.reports'

    def ready(self):
        from . import signals  # noqa: F401
