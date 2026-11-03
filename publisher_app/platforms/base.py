"""Shared contract used by all platform adapters."""
from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    name = "platform"
    capabilities = frozenset()

    @property
    @abstractmethod
    def logged_in(self):
        raise NotImplementedError

    @abstractmethod
    def login(self, username, password):
        raise NotImplementedError

    @abstractmethod
    def publish(self, article, images=(), **options):
        raise NotImplementedError

    @abstractmethod
    def update(self, article_id, article, images=(), **options):
        raise NotImplementedError
