from __future__ import annotations


class PrefixedSessionProxy:
    """Remaps session keys that start with ``old_prefix`` onto ``new_prefix``.

    Lets sample import reuse material-import session helpers without sharing keys.
    """

    __slots__ = ('_session', '_old', '_new')

    def __init__(self, session, old_prefix: str, new_prefix: str):
        object.__setattr__(self, '_session', session)
        object.__setattr__(self, '_old', old_prefix)
        object.__setattr__(self, '_new', new_prefix)

    def _map_key(self, key):
        if isinstance(key, str) and key.startswith(self._old):
            return self._new + key[len(self._old):]
        return key

    def __getattr__(self, name):
        return getattr(object.__getattribute__(self, '_session'), name)

    def __setattr__(self, name, value):
        if name in PrefixedSessionProxy.__slots__:
            object.__setattr__(self, name, value)
            return
        setattr(object.__getattribute__(self, '_session'), name, value)

    def __getitem__(self, key):
        return self._session[self._map_key(key)]

    def __setitem__(self, key, value):
        self._session[self._map_key(key)] = value

    def __delitem__(self, key):
        del self._session[self._map_key(key)]

    def __contains__(self, key):
        return self._map_key(key) in self._session

    def get(self, key, default=None):
        return self._session.get(self._map_key(key), default)

    def pop(self, key, *args):
        return self._session.pop(self._map_key(key), *args)

    def setdefault(self, key, default=None):
        return self._session.setdefault(self._map_key(key), default)

    def __bool__(self):
        return bool(self._session)
