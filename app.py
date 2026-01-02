"""
Hugging Face Spaces entry point
(Symlink/wrapper for optionchain.py)
"""

import sys
import os

# Hugging Face Spaces runs from root directory
# Ensure we can import from current directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import and run the main streamlit app
from optionchain import *

# The main code from optionchain.py will execute automatically
# when this file is imported by Streamlit
