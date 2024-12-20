from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.background import BackgroundTasks
from redis_om import HashModel, get_redis_connection
from starlette.requests import Request
import requests

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

class Order(HashModel):
    product_id: str
    price: float
    fee: float
    total: float
    quantity: int
    status: str

    class Meta:
        database = redis

@app.get("/orders/{pk}")
def get(pk: str):
    return Order.get(pk)

@app.post("/orders")
async def create(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    req = requests.get(f"http://inventory:8000/products/{body['product_id']}")
    product = req.json()
    order = Order(
        product_id=body['product_id'],
        price=product['price'],
        fee=0.2 * product['price'],
        total=1.2 * product['price'],
        quantity=body['quantity'],
        status="pending",
    )
    order.save()
    background_tasks.add_task(order_completed, order)
    return order

def order_completed(order: Order):
    order.status = "completed"
    order.save()
    redis.xadd("order_completed", order.dict(), "*")
    return order


