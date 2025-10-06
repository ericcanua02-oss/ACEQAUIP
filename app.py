import os
import json
import logging
from datetime import datetime

# Silence TensorFlow logs
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import numpy as np
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from tensorflow.keras.models import load_model  # pyright: ignore[reportMissingImports]
from tensorflow.keras.preprocessing import image  # pyright: ignore[reportMissingImports]
from flask_cors import CORS
from pymongo import MongoClient
from dotenv import load_dotenv
import certifi
import boto3 # pyright: ignore[reportMissingImports]
import tempfile
import requests

# ── Load environment ──────────────────────────────────────────────────────────
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET")

# ── Configuration ─────────────────────────────────────────────────────────────
UPLOAD_FOLDER = "uploads"
HISTORY_PATH = "history.json"
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "bmp"}
TARGET_SIZE = (150, 150)
CLASS_NAMES = ["Fresh", "Invalid", "Spoiled"]
MODEL_PATH = "updated_egg_advanced_model.keras"

# ── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
logging.basicConfig(level=logging.INFO)

# ── Ensure folders and files ──────────────────────────────────────────────────
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
if not os.path.isfile(HISTORY_PATH):
    with open(HISTORY_PATH, "w") as f:
        json.dump([], f)

# ── Load model ────────────────────────────────────────────────────────────────
MODEL_URL = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/updated_egg_advanced_model.keras"

try:
    response = requests.get(MODEL_URL)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(response.content)
        model = load_model(tmp.name)
    logging.info(f"✅ Loaded model from S3: {MODEL_URL}")
except Exception as e:
    logging.error(f"❌ Failed to load model from S3: {e}")
    model = None

# ── MongoDB connection ────────────────────────────────────────────────────────
try:
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

def get_scans_collection():
    global mongo_client, scans
    if scans is None:
        try:
            mongo_client = MongoClient(
                MONGO_URI,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000
            )
            mongo_client.admin.command("ping")
            db = mongo_client["egg_scanner"]
            scans = db["scan_history"]
            logging.info("✅ Reconnected to MongoDB Atlas")
        except Exception as e:
            logging.error(f"❌ MongoDB reconnection failed: {e}")
            scans = None
    return scans

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_history(entry: dict):
    scans_col = get_scans_collection()
    if scans_col is not None:
        try:
            scans_col.insert_one(entry)
            return
        except Exception as e:
            logging.warning(f"⚠️ Could not write to MongoDB: {e}")
    with open(HISTORY_PATH, "r+") as f:
        data = json.load(f)
        data.insert(0, entry)
        f.seek(0)
        json.dump(data[:20], f, indent=2)
        f.truncate()

# ── S3 setup ──────────────────────────────────────────────────────────────────
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION
)

def upload_to_s3(local_path, s3_key):
    try:
        s3.upload_file(local_path, S3_BUCKET, s3_key)
        url = f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"
        logging.info(f"✅ Uploaded to S3: {url}")
        return url
    except Exception as e:
        logging.error(f"❌ S3 upload failed: {e}")
        return None


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/predict", methods=["POST"])
def predict():
    if "file" not in request.files:
        return jsonify({"error": "No file field"}), 400
    f = request.files["file"]
    if f.filename == "" or not allowed_file(f.filename):
        return jsonify({"error": "Invalid file"}), 400

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    ext = f.filename.rsplit(".", 1)[1].lower()
    name = secure_filename(f"scan_{ts}.{ext}")
    local_path = os.path.join(UPLOAD_FOLDER, name)
    f.save(local_path)

    # Upload to S3
    s3_key = f"scans/{name}"
    s3_url = upload_to_s3(local_path, s3_key)

    img = image.load_img(local_path, target_size=TARGET_SIZE)
    arr = image.img_to_array(img) / 255.0
    preds = model.predict(np.expand_dims(arr, 0))[0]
    idx = int(np.argmax(preds))
    label = CLASS_NAMES[idx]
    conf = round(float(preds[idx]) * 100, 2)

    entry = {
        "filename": name,
        "result": label,
        "confidence": conf,
        "probs": {CLASS_NAMES[i]: float(round(preds[i] * 100, 2)) for i in range(len(preds))},
        "timestamp": datetime.utcnow(),
        "image_url": s3_url
    }

    save_history(entry)

    return jsonify({
        "result": label,
        "confidence": conf,
        "probs": entry["probs"],
        "image_url": s3_url
    }), 200

@app.route("/api/history", methods=["GET"])
def history():
    scans_col = get_scans_collection()
    if scans_col is not None:
        records = list(scans_col.find({}, {"_id": 0}).sort("timestamp", -1).limit(20))
        return jsonify(records), 200
    return jsonify({"error": "Database not connected"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
