"""LiveTimer - 只计时不打印，由 ThinkingUI 统一管理显示"""

import time
import threading


class LiveTimer:
    def __init__(self):
        self.seconds = 0
        self.running = False
        self.thread = None

    def start(self):
        self.seconds = 0
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            time.sleep(1)
            if self.running:
                self.seconds += 1

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)

    @property
    def elapsed(self):
        return self.seconds
