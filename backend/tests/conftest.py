import os
import sys
from pathlib import Path

# Isolated test database; must be set before app.config is imported.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# Real env vars beat .env files: unit tests never see the developer's real key or URL overrides.
os.environ["BHARATCODE_API_KEY"] = ""
os.environ["BHARATCODE_BASE_URL"] = "https://bharatcode.ai/api/model/v1"
os.environ["BHARATCODE_MODEL"] = "qwen-3.8-27b"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
