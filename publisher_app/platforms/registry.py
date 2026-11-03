"""Platform registry; add a new adapter here without changing the UI flow."""
from .yiliao import YiliaoPlatform
from .liaoshangbao import LiaoshangbaoPlatform


class PlatformRegistry:
    def __init__(self):
        self._platforms = {}

    def register(self, adapter):
        if adapter.name in self._platforms:
            raise ValueError("平台已注册：{}".format(adapter.name))
        self._platforms[adapter.name] = adapter

    def get(self, name):
        return self._platforms[name]

    def all(self):
        return tuple(self._platforms.values())


def default_registry():
    registry = PlatformRegistry()
    registry.register(YiliaoPlatform())
    registry.register(LiaoshangbaoPlatform())
    return registry
