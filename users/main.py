from fastapi import (
    FastAPI, 
    HTTPException, 
    Request, 
    Depends
)
from pydantic import BaseModel, EmailStr, Field
from redis import Redis
import uuid
from datetime import datetime
from abc import ABC, abstractmethod
from typing import Callable
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
from common.rate_limiter import RateLimitMiddleware
from common.logger import LoggerMiddleware
from common.config import settings
from common.events import (
    EventPublisher, 
    EventSubscriber,
    UserEvents,
    Topics,
)



class DatabaseClient:
    def __init__(
        self, 
        database_url: str,
        min_size: int = 5,
        max_size: int = 5,
        timeout: float = 30.0,
        command_timeout: float = 30.0
    ):
        self.database_url = database_url
        self._pool = None

    async def initialize(self):
        """Initialize the connection pool"""
        self._pool = await asyncpg.create_pool(
            self.database_url,
            min_size=5,          # Minimum connections in pool
            max_size=5,          # Maximum connections in pool
            timeout=30.0,        # Connection acquisition timeout
            command_timeout=30.0, # Query execution timeout
            max_inactive_connection_lifetime=300.0  # 5 minutes
        )
        return self

    async def close(self):
        """Close all connections in the pool"""
        if self._pool:
            await self._pool.close()

    async def fetch_all(self, query: str, *args):
        """Execute a query and return all results"""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetch_one(self, query: str, *args):
        """Execute a query and return one result"""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def execute(self, query: str, *args):
        """Execute a query without returning results"""
        if not self._pool:
            raise RuntimeError("Database pool not initialized")
        async with self._pool.acquire() as connection:
            return await connection.execute(query, *args)

# Connect to PostgresDatabase
database_client = DatabaseClient(settings.DATABASE_URL)

# Redis Key
USER_KEY = "users"  # Redis key to store all users as JSON objects

# User Model
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str
    last_name: str
    email: EmailStr
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: datetime = Field(default_factory=lambda: datetime.now().isoformat())

class UserExternal(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    is_active: bool
    created_at: datetime
    updated_at: datetime

class UserInterface(ABC):
    @abstractmethod
    def get_all_users(self):
        pass

    @abstractmethod
    def create_user(self, user: User):
        pass

    @abstractmethod
    def update_user(self, user_id: str, user: User):
        pass

    @abstractmethod
    def deactivate_user(self, user_id: str):
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: str):
        pass

    @abstractmethod
    def get_user_by_email(self, email: EmailStr):
        pass

class UserPostgresRepository(UserInterface):
    def __init__(self, database_client: DatabaseClient):
        self.database_client = database_client

    async def get_all_users(self):
        return await self.database_client.fetch_all("""
            SELECT * FROM users
        """)  

    async def create_user(self, user: User):
        return await self.database_client.execute("""
            INSERT INTO users (id, first_name, last_name, email, is_active, created_at, updated_at) 
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """, user.id, user.first_name, user.last_name, user.email, user.is_active, user.created_at, user.updated_at)

    async def update_user(self, user_id: str, user: User):
        return await self.database_client.execute("""
            UPDATE users 
            SET first_name = $1, last_name = $2, email = $3, is_active = $4, updated_at = $5 
            WHERE id = $6
        """, user.first_name, user.last_name, user.email, user.is_active, user.updated_at, user_id)

    async def deactivate_user(self, user_id: str):
        return await self.database_client.execute("""
            UPDATE users 
            SET is_active = false 
            WHERE id = $1
        """, user_id)

    async def get_user_by_id(self, user_id: str):
        return await self.database_client.fetch_one("""
            SELECT * FROM users 
            WHERE id = $1
        """, user_id)

    async def get_user_by_email(self, email: EmailStr):
        return await self.database_client.fetch_one("""
            SELECT * FROM users 
            WHERE email = $1
        """, email)

def get_user_postgres_repository(database_client: DatabaseClient):
    return UserPostgresRepository(database_client)

# class UserRedisCacheRepository(UserInterface):
#     def __init__(self, redis_client: Redis, ttl: int = 60 * 60 * 24):
#         self.redis_client = redis_client
#         self.ttl = ttl
 
#     async def get_all_users(self):
#         keys = await self.redis_client.keys(f"{USER_KEY}:{function_name}*")
#         users = [await self.redis_client.json().get(key) for key in keys]
#         return {"users": users}

#     async def create_user(self, user: User):
#         user_id = user.id
#         user_data = user.dict()
#         await self.redis_client.json().set(f"{USER_KEY}:{user_id}", ".", user_data)
#         return {"message": "User created successfully", "user": user_data}

#     async def update_user(self, user_id: str, user: User):
#         user_data = user.dict()
#         await self.redis_client.json().set(f"{USER_KEY}:{user_id}", ".", user_data)
#         return {"message": "User updated successfully", "user": user_data}

#     async def deactivate_user(self, user_id: str):
#         user_data = await self.redis_client.json().get(f"{USER_KEY}:{user_id}")
#         if not user_data:
#             raise HTTPException(status_code=404, detail="User not found")
#         user_data["is_active"] = False
#         await self.redis_client.json().set(f"{USER_KEY}:{user_id}", ".", user_data)
#         return {"message": "User deactivated successfully", "user": user_data}

#     async def get_user_by_id(self, user_id: str):
#         user_data = await self.redis_client.json().get(f"{USER_KEY}:{user_id}")
#         if not user_data:
#             raise HTTPException(status_code=404, detail="User not found")
#         return user_data

#     async def get_user_by_email(self, email: EmailStr):
#         keys = await self.redis_client.keys(f"{USER_KEY}:*")
#         users = [await self.redis_client.json().get(key) for key in keys if await self.redis_client.json().get(key)["email"] == email]
#         return {"users": users}

# def get_user_redis_repository(redis_client: Redis):
#     return UserRedisCacheRepository(redis_client)

class UserService(UserInterface):
    def __init__(self, 
        user_db_repository: UserPostgresRepository,
        # user_cache_repository: UserRedisCacheRepository
    ):
        self.user_db_repository = user_db_repository
        # self.user_cache_repository = user_cache_repository

    async def create_user(self, user: User):
        return await self.user_db_repository.create_user(user)

    async def get_all_users(self):
        return await self.user_db_repository.get_all_users()

    async def update_user(self, user_id: str, user: User):
        return await self.user_db_repository.update_user(user_id, user)

    async def deactivate_user(self, user_id: str):
        return await self.user_db_repository.deactivate_user(user_id)

    async def get_user_by_id(self, user_id: str):
        return await self.user_db_repository.get_user_by_id(user_id)

    async def get_user_by_email(self, email: EmailStr):
        return await self.user_db_repository.get_user_by_email(email)

def get_user_service(db_repository: UserPostgresRepository):
    return UserService(db_repository)

# dependencies
def get_user_service_dependency(request: Request):
    user_service = request.app.state.user_service
    if not user_service:
        raise HTTPException(status_code=500, detail="User service not initialized")
    return user_service

async def lifespan(app: FastAPI):   
    redis_client = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=10.0,
        retry_on_timeout=True
    )
    app.state.user_service = get_user_service(
        get_user_postgres_repository(database_client)
        # get_user_redis_repository(redis_client)
    )
    app.state.rate_limiter = RateLimitMiddleware(
        redis_client=redis_client,
        requests_per_minute=settings.RATE_LIMIT_REQUESTS
    )
    app.state.logger = LoggerMiddleware(
        app_name="users"
    )
    app.state.publisher = EventPublisher(
        event_types=UserEvents,
        redis_client=redis_client,
        channel=Topics.USERS
    )

    app.state.subscriber = EventSubscriber(
        event_types=UserEvents,
        redis_client=redis_client,
        channel=Topics.USERS
    )
    await app.state.subscriber.start_background()
    yield
    await app.state.subscriber.stop()

def create_app():
    # Initialize FastAPI
    app = FastAPI(lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next: Callable):
        return await app.state.rate_limiter(request, call_next)
    
    @app.middleware("http")
    async def logger_middleware(request: Request, call_next: Callable):
        return await app.state.logger(request, call_next)
    
    return app

app = create_app()

@app.get("/health")
async def health():
    # TODO: return the health of the service
    return {"status": "ok"}

@app.get("/metrics")
async def metrics():
    # TODO: return the metrics of the service
    return {"status": "ok"}


# Create User
@app.post("/users", status_code=201)
async def create_user(
    user: UserExternal, 
):
    user_data = User(**user.model_dump())
    await app.state.user_service.create_user(user_data)
    await app.state.publisher.publish(UserEvents.USER_CREATED, user)
    return {
        "message": "User created successfully", 
        "data": {
            "user": user.model_dump()
        },
        "timestamp": datetime.now().isoformat()
    }

# Get All Users
@app.get("/users")
async def get_all_users():
    return await app.state.user_service.get_all_users()

# Get User by ID
@app.get("/users/{user_id}")
async def get_user(
    user_id: str, 
):
    return await app.state.user_service.get_user_by_id(user_id)

# Update User
@app.put("/users/{user_id}")
async def update_user(
    user_id: str, 
    updated_user: User, 
):
    return await app.state.user_service.update_user(user_id, updated_user)

# Partially Update User (PATCH)
@app.patch("/users/{user_id}")
async def patch_user(
    user_id: str, 
    updates: dict, 
):
    user = await app.state.user_service.get_user_by_id(user_id)  # Check if the user exists
    
    # Apply updates to the user
    for key, value in updates.items():
        user[key] = value
    
    # Save updated user
    return await app.state.user_service.update_user(user_id, user)

# Delete User
@app.delete("/users/{user_id}")
async def delete_user(
    user_id: str, 
):
    return await app.state.user_service.delete_user(user_id)