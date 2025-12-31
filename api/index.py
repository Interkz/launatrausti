"""
Vercel serverless function entry point.
"""
import sys
from pathlib import Path

# Add the project root to the path so we can import src modules
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from src.main import app

# Vercel expects the app to be named 'app' or 'handler'
# FastAPI apps work directly with Vercel's Python runtime
