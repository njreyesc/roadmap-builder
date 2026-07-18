"""Делает модули из ../scripts импортируемыми в тестах."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
