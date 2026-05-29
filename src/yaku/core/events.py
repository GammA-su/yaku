"""Lightweight in-process event bus."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Event:
    name: str
    data: Any = field(default=None)


_listeners: dict[str, list[Callable[[Event], None]]] = defaultdict(list)


def subscribe(event_name: str, handler: Callable[[Event], None]) -> None:
    _listeners[event_name].append(handler)


def unsubscribe(event_name: str, handler: Callable[[Event], None]) -> None:
    _listeners[event_name].remove(handler)


def emit(event: Event) -> None:
    for handler in list(_listeners[event.name]):
        handler(event)


def emit_named(name: str, data: Any = None) -> None:
    emit(Event(name=name, data=data))


def clear_all() -> None:
    _listeners.clear()
