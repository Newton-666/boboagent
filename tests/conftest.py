"""
tests/conftest.py - 测试配置：统一将项目根目录加入 sys.path
"""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
