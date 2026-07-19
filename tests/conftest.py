import os
import sys
from pathlib import Path

# Permite `pytest` de qualquer lugar
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# valores mínimos para evitar erro de Settings em testes
os.environ.setdefault("GOOGLE_API_KEY", "test")
os.environ.setdefault("APP_ENV", "local")
