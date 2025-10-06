import os

MODEL_PATH = "updated_egg_advanced_model.keras"

print("Exists:", os.path.exists(MODEL_PATH))
print("Is file:", os.path.isfile(MODEL_PATH))
print("Size:", os.path.getsize(MODEL_PATH))
