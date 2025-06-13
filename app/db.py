from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError
import os

client = None
db = None

async def connect_to_mongo():
    global client, db
    mongo_user = os.getenv("MONGO_USER", "root")
    mongo_pass = os.getenv("MONGO_PASS", "example")
    mongo_host = os.getenv("MONGO_HOST", "mongo")
    mongo_port = int(os.getenv("MONGO_PORT", 27017))
    mongo_db = os.getenv("MONGO_DB", "iot")

    uri = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/admin"

    try:
        client = AsyncIOMotorClient(uri)
        db = client[mongo_db]
        print("✅ Conectado a MongoDB con Motor")
    except PyMongoError as e:
        print("❌ Error de conexión a MongoDB:", e)

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("🔌 Conexión a MongoDB cerrada")

def get_db():
    global db
    return db