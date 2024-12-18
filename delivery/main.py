from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis_om import HashModel, get_redis_connection
from starlette.requests import Request
import json
from pydantic import BaseModel
from subscriber import subscriptions
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis = get_redis_connection(
    host="redis",
    port=6379,
    decode_responses=True
)

class Delivery(HashModel):
    budget: float = 0
    notes: str = ""

    class Meta:
        database = redis

class Event(HashModel):
    delivery_id: str = None
    type: str
    data: str

    class Meta:
        database = redis

@app.get("/delivery/{pk}/status")
def get_delivery_status(pk: str):
    state = redis.get(f"delivery:{pk}")

    if state is None:
        return json.loads(state)

    state = build_state(pk)
    redis.set(f"delivery:{pk}", json.dumps(state))
    return state

def build_state(pk: str):
    pks = Event.all_pks()
    events = [Event.get(pk) for pk in pks]
    events = sorted(events, key=lambda x: x.created_at)

    state = {}
    for event in events:
        state = subscriptions[event.type](state, event)

    return state

    delivery = Delivery.get(pk)
    state = {
        "budget": delivery.budget,
        "quantity": 0,
        "status": "ready",
    }
    return state

@app.post("/delivery")
async def create(request: Request):
    body = await request.json()
    delivery = Delivery(budget=body["data"]["budget"], notes=body["data"]["notes"])
    delivery.save()
    event = Event(delivery_id=delivery.pk, type=body["type"], data=json.dumps(body["data"]))
    event.save()
    state = subscriptions[event.type](state=None, event=event)      
    redis.set(f"delivery:{delivery.pk}", json.dumps(state))
    return state

@app.post("/event")
async def dispatch(request: Request):
    body = await request.json()
    delivery_id = body["data"]["delivery_id"]
    state = await get_delivery_status(delivery_id)
    event = Event(delivery_id=delivery_id, type=body["type"], data=json.dumps(body["data"]))
    new_state = subscriptions[event.type](state=state, event=event)
    redis.set(f"delivery:{delivery_id}", json.dumps(new_state))
    return new_state