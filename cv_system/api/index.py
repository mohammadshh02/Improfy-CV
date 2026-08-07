"""Einstiegspunkt für Vercel, wenn Root Directory auf `cv_system` steht.

Zwillingsdatei zu ../../api/index.py (greift, wenn Root Directory die
Repo-Wurzel ist). Beide Varianten liegen im Repo, damit das Deployment
unabhaengig von der Projekteinstellung funktioniert.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app  # noqa: E402

__all__ = ["app"]
