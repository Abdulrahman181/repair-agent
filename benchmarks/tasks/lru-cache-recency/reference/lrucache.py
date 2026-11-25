class LRUCache:
    """Least-recently-used cache with a fixed capacity.

    Both get and put count as a use of the key. When a new key is added to a full cache, the
    least recently used key is evicted. Updating an existing key never evicts anything. A
    capacity below 1 raises ValueError. get returns None for a missing key.
    """

    def __init__(self, capacity):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self._data = {}

    def get(self, key):
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def put(self, key, value):
        if key in self._data:
            del self._data[key]
        elif len(self._data) >= self.capacity:
            oldest = next(iter(self._data))
            del self._data[oldest]
        self._data[key] = value

    def __len__(self):
        return len(self._data)
