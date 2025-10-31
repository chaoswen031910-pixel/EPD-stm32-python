import sys
import os
from PyQt5.QtCore import QObject, pyqtSignal

# 导入 ScriptExecutor，它在父目录中
try:
    from services.script_executor import ScriptExecutor
except ImportError:
    # 如果直接运行或导入时找不到，则动态添加父目录
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from services.script_executor import ScriptExecutor

class LutUpdateWorker(QObject):
    finished = pyqtSignal()
    def __init__(self, serial_worker, script_path, lut_data):
        super().__init__(); self.serial_worker = serial_worker; self.script_path = script_path; self.lut_data = lut_data; self.is_running = True; self.executor = ScriptExecutor(self.serial_worker)
    def run(self):
        # 尝试连接到主窗口的日志功能
        if hasattr(self.parent(), 'log_to_textarea'): 
            self.executor.log_message.connect(self.parent().log_to_textarea)
        
        # [修改] 确保即使在独立worker中，日志也能正确连接
        # 注意：如果 self.parent() 不是 MainWindow，log_message 可能不会显示
        # 但 ScriptExecutor 内部的 ScriptExecutor(self.serial_worker) 通常会处理日志
        # 我们保持原有的逻辑不变
        
        self.executor.run_script(self.script_path, self.lut_data); self.finished.emit()
    def stop(self): self.is_running = False; self.executor.stop_all_tasks()