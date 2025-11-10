import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Local imports with support for both "python -m src.main" and "python src/main.py"
try:  # When run as a module: python -m src.main
from .extractors.company_parser import search_companies
from .extractors.utils_filters import apply_company_filters
from .outputs.exporter import export_companies