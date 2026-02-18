from django.apps import AppConfig


class WebappConfig(AppConfig):
    name = 'webapp'

    def ready(self):
        from . import signals  # noqa: F401
