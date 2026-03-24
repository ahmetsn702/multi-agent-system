"""
conftest.py
Pytest configuration file that adds the project root to sys.path.
This allows tests to use absolute imports like "from agents.xxx import yyy".
"""
import sys
import os

# Get the absolute path to the multi_agent_system directory (where this conftest.py is)
project_root = os.path.abspath(os.path.dirname(__file__))

# Add project root at the beginning of sys.path for absolute imports
if project_root in sys.path:
    sys.path.remove(project_root)
sys.path.insert(0, project_root)
