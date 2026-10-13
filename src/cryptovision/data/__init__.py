"""Historical market data pipeline: configuration, collection, validation and storage.

Nothing in this package performs network requests at import time. Live
collection only happens through an explicit `collect` call.
"""
