"""
Messaging abstraction for distributed coordination.

Provides a unified interface that works with:
1. Local multiprocessing (fallback when NATS unavailable)
2. NATS pub/sub (when nats-py is installed)

The abstraction allows the coordinator to work identically
regardless of the underlying transport.
"""

import json
import queue
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional, Any


@dataclass
class Message:
    """A message in the coordination system."""
    topic: str
    payload: dict
    reply_to: Optional[str] = None


class MessageBus(ABC):
    """Abstract message bus interface."""

    @abstractmethod
    def publish(self, topic: str, payload: dict) -> None:
        """Publish a message to a topic."""
        pass

    @abstractmethod
    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe to a topic with a handler."""
        pass

    @abstractmethod
    def request(self, topic: str, payload: dict, timeout: float = 5.0) -> Optional[dict]:
        """Send a request and wait for response."""
        pass

    @abstractmethod
    def start(self) -> None:
        """Start the message bus."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the message bus."""
        pass


class LocalMessageBus(MessageBus):
    """Local in-memory message bus using queues."""

    def __init__(self):
        self.subscribers: dict[str, list[Callable[[Message], None]]] = {}
        self.response_queues: dict[str, queue.Queue] = {}
        self.running = False
        self._lock = threading.Lock()

    def publish(self, topic: str, payload: dict) -> None:
        """Publish to local subscribers."""
        msg = Message(topic=topic, payload=payload)

        with self._lock:
            handlers = self.subscribers.get(topic, [])

        for handler in handlers:
            try:
                handler(msg)
            except Exception as e:
                print(f"Handler error on {topic}: {e}")

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe a handler to a topic."""
        with self._lock:
            if topic not in self.subscribers:
                self.subscribers[topic] = []
            self.subscribers[topic].append(handler)

    def request(self, topic: str, payload: dict, timeout: float = 5.0) -> Optional[dict]:
        """Send request and wait for response."""
        import uuid
        reply_topic = f"reply.{uuid.uuid4()}"
        response_queue: queue.Queue = queue.Queue()

        def response_handler(msg: Message):
            response_queue.put(msg.payload)

        self.subscribe(reply_topic, response_handler)

        msg = Message(topic=topic, payload=payload, reply_to=reply_topic)
        with self._lock:
            handlers = self.subscribers.get(topic, [])

        for handler in handlers:
            try:
                handler(msg)
            except Exception as e:
                print(f"Handler error: {e}")

        try:
            return response_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def respond(self, reply_to: str, payload: dict) -> None:
        """Send a response to a request."""
        self.publish(reply_to, payload)

    def start(self) -> None:
        """Start the bus."""
        self.running = True

    def stop(self) -> None:
        """Stop the bus."""
        self.running = False


class NatsMessageBus(MessageBus):
    """NATS-based message bus (requires nats-py)."""

    def __init__(self, server: str = "nats://localhost:4222"):
        self.server = server
        self.nc = None
        self.subscriptions = []

    def publish(self, topic: str, payload: dict) -> None:
        """Publish to NATS."""
        if self.nc is None:
            raise RuntimeError("NATS not connected")

        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            self.nc.publish(topic, json.dumps(payload).encode())
        )

    def subscribe(self, topic: str, handler: Callable[[Message], None]) -> None:
        """Subscribe to NATS topic."""
        if self.nc is None:
            raise RuntimeError("NATS not connected")

        import asyncio

        async def nats_handler(msg):
            payload = json.loads(msg.data.decode())
            m = Message(topic=topic, payload=payload, reply_to=msg.reply)
            handler(m)

        loop = asyncio.get_event_loop()
        sub = loop.run_until_complete(self.nc.subscribe(topic, cb=nats_handler))
        self.subscriptions.append(sub)

    def request(self, topic: str, payload: dict, timeout: float = 5.0) -> Optional[dict]:
        """NATS request-reply."""
        if self.nc is None:
            raise RuntimeError("NATS not connected")

        import asyncio

        async def do_request():
            response = await self.nc.request(
                topic,
                json.dumps(payload).encode(),
                timeout=timeout
            )
            return json.loads(response.data.decode())

        loop = asyncio.get_event_loop()
        try:
            return loop.run_until_complete(do_request())
        except Exception:
            return None

    def start(self) -> None:
        """Connect to NATS."""
        try:
            import nats
            import asyncio

            async def connect():
                self.nc = await nats.connect(self.server)

            loop = asyncio.get_event_loop()
            loop.run_until_complete(connect())
            print(f"Connected to NATS at {self.server}")

        except ImportError:
            raise RuntimeError("nats-py not installed. Install with: pip install nats-py")

    def stop(self) -> None:
        """Disconnect from NATS."""
        if self.nc:
            import asyncio

            async def disconnect():
                await self.nc.drain()

            loop = asyncio.get_event_loop()
            loop.run_until_complete(disconnect())


def create_message_bus(use_nats: bool = False, nats_server: str = "nats://localhost:4222") -> MessageBus:
    """Factory function to create appropriate message bus."""
    if use_nats:
        try:
            import nats
            return NatsMessageBus(nats_server)
        except ImportError:
            print("NATS not available, falling back to local bus")
            return LocalMessageBus()
    return LocalMessageBus()


# Message types for the scheduling system
TOPIC_WORK_REQUEST = "scheduler.work.request"
TOPIC_WORK_RESULT = "scheduler.work.result"
TOPIC_ARCHIVE_UPDATE = "scheduler.archive.update"
TOPIC_PARAM_SUGGESTION = "scheduler.params.suggestion"


def encode_work_request(seed: int, params: dict) -> dict:
    """Encode a work request message."""
    return {
        "type": "work_request",
        "seed": seed,
        "params": params
    }


def encode_work_result(seed: int, coverage: float, hard: int, soft: int, time_ms: int) -> dict:
    """Encode a work result message."""
    return {
        "type": "work_result",
        "seed": seed,
        "coverage": coverage,
        "hard_violations": hard,
        "soft_cost": soft,
        "time_ms": time_ms
    }
