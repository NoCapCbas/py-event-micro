from redis import Redis
from datetime import datetime
import json
from typing import Any, Callable, Dict, List
from enum import Enum
from dataclasses import dataclass
import asyncio

@dataclass
class Event:
    type: str
    data: Dict[str, Any]
    timestamp: datetime

@dataclass
class EventMetadata:
    name: str
    description: str
    version: str = "1.0"
    schema: Dict[str, Any] = None

class Topics:
    USERS = "users"
    EMAILS = "emails"

class EventType:
    pass

class UserEvents(EventType):
    REGISTERED = "user.registered"
    DEACTIVATED = "user.deactivated"
    LOGIN = "user.login"
    LOGOUT = "user.logout"

    # Event metadata
    _events_metadata = {
        REGISTERED: EventMetadata(
            name=REGISTERED,
            description="User registration event",
            schema={
                "user_id": "string",
                "email": "string",
                "created_at": "datetime"
            }
        ),
        DEACTIVATED: EventMetadata(
            name=DEACTIVATED,
            description="User deactivation event",
            schema={
                "user_id": "string",
                "reason": "string",
                "deactivated_at": "datetime"
            }
        ),
        LOGIN: EventMetadata(
            name=LOGIN,
            description="User login event",
            schema={
                "user_id": "string",
                "ip_address": "string",
                "login_at": "datetime"
            }
        ),
        LOGOUT: EventMetadata(
            name=LOGOUT,
            description="User logout event",
            schema={
                "user_id": "string",
                "logout_at": "datetime"
            }
        )
    }

    @classmethod
    def list_events(cls) -> List[str]:
        """Return list of all event types"""
        return [
            event for event in vars(cls) 
            if not event.startswith('_') and isinstance(getattr(cls, event), str)
        ]

    @classmethod
    def get_event_metadata(cls, event_type: str) -> EventMetadata:
        """Get metadata for specific event type"""
        return cls._events_metadata.get(event_type)

    @classmethod
    def get_all_events_metadata(cls) -> Dict[str, EventMetadata]:
        """Get metadata for all events"""
        return cls._events_metadata

    @staticmethod
    def create_event(event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create an event with standard format"""
        return {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0",
            "data": data
        }

    @staticmethod
    def register_user(user_id: str):
        return {
            "type": UserEvents.REGISTERED,
            "data": {"user_id": user_id}
        }

    @staticmethod
    def deactivate_user(user_id: str):
        return {
            "type": UserEvents.DEACTIVATED,
            "data": {"user_id": user_id}
        }

    @staticmethod
    def login_user(user_id: str):
        return {
            "type": UserEvents.LOGIN,
            "data": {"user_id": user_id}
        }

    @staticmethod
    def logout_user(user_id: str):
        return {
            "type": UserEvents.LOGOUT,
            "data": {"user_id": user_id}
        }

class EventPublisher:
    def __init__(self, event_types: EventType, redis_client: Redis, channel: str = "users"):
        self.event_types = event_types
        self.redis = redis_client
        self.channel = channel

    async def publish(self, event_type: str, data: Any):
        if event_type not in self.event_types.list_events():
            raise ValueError(f"Invalid event type: {event_type}")
        message = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        }
        await self.redis.publish(self.channel, json.dumps(message))

class EventSubscriber:
    def __init__(self, event_types: EventType, redis_client: Redis, channel: str = "users"):
        self.event_types = event_types
        self.redis = redis_client
        self.channel = channel
        self.handlers: Dict[str, Callable] = {}

    def register_event_types(self):
        for event in self.event_types.list_events():
            self.handlers[event] = event

    def register_handler(self, event_type: str, handler: Callable):
        self.handlers[event_type] = handler

    async def start_background(self):
        """Start subscriber in background task"""
        self.task = asyncio.create_task(self.start())
        return self.task

    async def stop(self):
        """Stop the subscriber"""
        if hasattr(self, 'task'):
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

    async def start(self):
        try:
            pubsub = self.redis.pubsub()
            await pubsub.subscribe(self.channel)

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                if message:
                    data = json.loads(message["data"])
                    handler = self.handlers.get(data["type"])
                    if handler:
                        # Handle each message in a separate task
                        asyncio.create_task(handler(data["data"]))
                await asyncio.sleep(0.01)  # Prevent CPU spinning
        except asyncio.CancelledError:
            await pubsub.unsubscribe()
            raise
