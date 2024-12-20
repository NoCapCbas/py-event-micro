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
from common.rate_limiter import RateLimitMiddleware
from common.logger import LoggerMiddleware
from common.config import settings


# Connect to Redis
redis_client = Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True
)

# Redis Key
USER_KEY = "users"  # Redis key to store all users as JSON objects

# User Model
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    first_name: str
    last_name: str
    email: EmailStr
    age: int = Field(..., ge=0, le=120, description="Age must be between 0 and 120")
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

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
    def delete_user(self, user_id: str):
        pass

    @abstractmethod
    def get_user_by_id(self, user_id: str):
        pass

    @abstractmethod
    def get_user_by_email(self, email: EmailStr):
        pass

class UserRedisRepository(UserInterface):
    def __init__(self, redis_client: Redis):
        self.redis_client = redis_client
 
    async def get_all_users(self):
        keys = await self.redis_client.keys(f"{USER_KEY}:*")
        users = [await self.redis_client.json().get(key) for key in keys]
        return {"users": users}

    async def create_user(self, user: User):
        user_id = user.id
        user_data = user.dict()
        await self.redis_client.json().set(f"{USER_KEY}:{user_id}", ".", user_data)
        return {"message": "User created successfully", "user": user_data}

    async def update_user(self, user_id: str, user: User):
        user_data = user.dict()
        await self.redis_client.json().set(f"{USER_KEY}:{user_id}", ".", user_data)
        return {"message": "User updated successfully", "user": user_data}

    async def delete_user(self, user_id: str):
        await self.redis_client.delete(f"{USER_KEY}:{user_id}")
        return {"message": "User deleted successfully"}

    async def get_user_by_id(self, user_id: str):
        user_data = await self.redis_client.json().get(f"{USER_KEY}:{user_id}")
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
        return user_data

    async def get_user_by_email(self, email: EmailStr):
        keys = await self.redis_client.keys(f"{USER_KEY}:*")
        users = [await self.redis_client.json().get(key) for key in keys if await self.redis_client.json().get(key)["email"] == email]
        return {"users": users}

def get_user_redis_repository(redis_client: Redis):
    return UserRedisRepository(redis_client)

class UserService(UserInterface):
    def __init__(self, user_cache_repository: UserRedisRepository):
        self.user_cache_repository = user_cache_repository

    async def create_user(self, user: User):
        return await self.user_cache_repository.create_user(user)

    async def get_all_users(self):
        return await self.user_cache_repository.get_all_users()

    async def update_user(self, user_id: str, user: User):
        return await self.user_cache_repository.update_user(user_id, user)

    async def delete_user(self, user_id: str):
        return await self.user_cache_repository.delete_user(user_id)

    async def get_user_by_id(self, user_id: str):
        return await self.user_cache_repository.get_user_by_id(user_id)

    async def get_user_by_email(self, email: EmailStr):
        return await self.user_cache_repository.get_user_by_email(email)

def get_user_service(cache_repository: UserRedisRepository):
    return UserService(cache_repository)

# dependencies
def get_user_service_dependency(request: Request):
    user_service = request.app.state.user_service
    if not user_service:
        raise HTTPException(status_code=500, detail="User service not initialized")
    return user_service

async def lifespan(app: FastAPI):   
    app.state.user_service = get_user_service(get_user_redis_repository(redis_client))
    app.state.rate_limiter = RateLimitMiddleware(
        redis_client=redis_client,
        requests_per_minute=settings.RATE_LIMIT_REQUESTS
    )
    app.state.logger = LoggerMiddleware(
        app_name="users"
    )
    yield

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
    user: User, 
    user_service: UserService = Depends(get_user_service_dependency)
):
    return await user_service.create_user(user)

# Get All Users
@app.get("/users")
async def get_all_users(
    user_service: UserService = Depends(get_user_service_dependency)
):
    return await user_service.get_all_users()

# Get User by ID
@app.get("/users/{user_id}")
async def get_user(
    user_id: str, 
    user_service: UserService = Depends(get_user_service_dependency)
):
    return await user_service.get_user_by_id(user_id)

# Update User
@app.put("/users/{user_id}")
async def update_user(
    user_id: str, 
    updated_user: User, 
    user_service: UserService = Depends(get_user_service_dependency)
):
    return await user_service.update_user(user_id, updated_user)

# Partially Update User (PATCH)
@app.patch("/users/{user_id}")
async def patch_user(
    user_id: str, 
    updates: dict, 
    user_service: UserService = Depends(get_user_service_dependency)
):
    user = await user_service.get_user_by_id(user_id)  # Check if the user exists
    
    # Apply updates to the user
    for key, value in updates.items():
        user[key] = value
    
    # Save updated user
    return await user_service.update_user(user_id, user)

# Delete User
@app.delete("/users/{user_id}")
async def delete_user(
    user_id: str, 
    user_service: UserService = Depends(get_user_service_dependency)
):
    return await user_service.delete_user(user_id)