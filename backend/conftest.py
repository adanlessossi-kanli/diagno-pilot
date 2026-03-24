import sys
import os

# Add the parent directory (project root) to sys.path so that
# "from backend.models import ..." works when running pytest from backend/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
