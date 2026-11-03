class PublishingService:
    """Coordinates a shared article operation across selected adapters."""
    def __init__(self, registry):
        self.registry = registry

    def publish(self, platform_names, article, images=(), options=None):
        options = options or {}
        results = {}
        errors = {}
        for name in platform_names:
            adapter = self.registry.get(name)
            try:
                if not adapter.logged_in:
                    raise RuntimeError("{} 尚未登录".format(name))
                results[name] = adapter.publish(article, images, **options.get(name, {}))
            except Exception as exc:
                errors[name] = str(exc)
        return {"results": results, "errors": errors}

    def update(self, platform_name, article_id, article, images=(), **options):
        adapter = self.registry.get(platform_name)
        if not adapter.logged_in:
            raise RuntimeError("{} 尚未登录".format(platform_name))
        return adapter.update(article_id, article, images, **options)
