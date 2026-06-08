"""性能追踪器 - 记录每一步的耗时"""

import time
from datetime import datetime
from functools import wraps

class Tracer:
    def __init__(self):
        self.enabled = True
        self.steps = []
    
    def start(self, name: str):
        if not self.enabled:
            return
        self.steps.append({
            "name": name,
            "start": time.time(),
            "end": None
        })
    
    def end(self, name: str = None):
        if not self.enabled:
            return
        if name:
            for step in self.steps:
                if step["name"] == name and step["end"] is None:
                    step["end"] = time.time()
                    break
        else:
            if self.steps:
                self.steps[-1]["end"] = time.time()
    
    def report(self):
        if not self.steps:
            return "\n没有追踪数据"
        
        result = "\n" + "=" * 60
        result += "\n⏱️ 性能追踪报告"
        result += "\n" + "=" * 60
        total = 0
        for step in self.steps:
            if step["end"]:
                elapsed = step["end"] - step["start"]
                total += elapsed
                result += f"\n  {step['name']}: {elapsed:.2f}s"
        result += f"\n" + "-" * 40
        result += f"\n  总计: {total:.2f}s"
        result += "\n" + "=" * 60
        return result
    
    def clear(self):
        self.steps = []

# 全局实例
_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer

def trace(name):
    """装饰器：自动追踪函数耗时"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = get_tracer()
            tracer.start(name)
            try:
                result = func(*args, **kwargs)
                tracer.end(name)
                return result
            except Exception as e:
                tracer.end(name)
                raise e
        return wrapper
    return decorator
