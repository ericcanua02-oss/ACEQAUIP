import certifi
from pymongo import MongoClient

# MongoDB connection
MONGO_URI = "mongodb+srv://ericcanua02_db_user:KgFGXct44hMF3Ywj@eggscannercluster.e3unheu.mongodb.net/egg_scanner?retryWrites=true&w=majority"

try:
    # Force TLS to use certifi bundle
    mongo_client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsCAFile=certifi.where(),
        serverSelectionTimeoutMS=5000
    )
    db = mongo_client["egg_scanner"]
    scans = db["scan_history"]
    print("✅ Connected to MongoDB!")
except Exception as e:
    mongo_client = None
    scans = None
    print(f"❌ MongoDB connection failed: {e}")
