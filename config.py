"""
config.py: This file contains general static variables and project_root
directory
"""

from pathlib import Path

project_root = Path(__file__).resolve().parent

# TODO: Revisit - most likely ticker list will be a csv data load
ticker_list = ['2267.T', '3435.T', '1846.HK', '6889.HK', '7399.T', '1913.HK', 'VTU.L', '0700.HK']