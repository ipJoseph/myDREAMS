"""
DREAMS Platform
Desktop Real Estate Agent Management System

An intelligent real estate operations platform that transforms manual
workflows into automated, predictive systems for matching buyers to properties.
"""

__version__ = "0.1.0"
__author__ = "Joseph"
__email__ = "joseph@integritypursuits.com"

from .core.database import DREAMSDatabase
from .core.matching_engine import MatchingEngine

__all__ = ["DREAMSDatabase", "MatchingEngine"]
