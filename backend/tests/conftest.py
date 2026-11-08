import os
import sys
from pathlib import Path

# Isolated test database; must be set before app.config is imported.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTH_ENABLED"] = "false"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
