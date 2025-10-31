import sys
import os
from PyQt5.QtCore import QObject, pyqtSignal, QThread

# 导入 ScriptExecutor，它在父目录中
try:
    from services.script_executor import ScriptExecutor
except ImportError:
    # 如果直接运行或导入时找不到，则动态添加父目录
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from services.script_executor import ScriptExecutor

class FlowWorker(QObject):
    finished = pyqtSignal(bool, str)
    log_message = pyqtSignal(str, bool)
    def __init__(self, serial_worker, profile, steps, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.profile = profile
        self.steps = steps
        self.is_running = True
    def run(self):
        total_steps = len(self.steps)
        for i, step in enumerate(self.steps):
            if not self.is_running: self.finished.emit(False, "流程被用户取消"); return
            step_name = step.get('name', step.get('type'))
            self.log_message.emit(f"[FLOW] 执行步骤 {i+1}/{total_steps}: {step_name}", False)
            step_type = step.get("type")
            success, message = False, f"未知步骤类型: {step_type}"
            try:
                if step_type == "init": success, message = self._execute_init_step(step)
                elif step_type == "script": success, message = self._execute_script_step(step)
                if not success: self.finished.emit(False, f"步骤 '{step_name}' 失败: {message}"); return
            except Exception as e:
                self.finished.emit(False, f"执行步骤 '{step_name}' 时发生意外错误: {e}"); return
        self.finished.emit(True, "流程执行完毕")
    def _execute_script_step(self, step):
        script_key = step.get("key");
        if not script_key: return False, "流程步骤'script'缺少'key'参数"
        scripts = self.profile.get("scripts", {}); relative_script_path = scripts.get(script_key)
        if not relative_script_path: return False, f"未在Profile的scripts中找到名为'{script_key}'的脚本"
        return self._run_script_file(relative_script_path)
    def _execute_init_step(self, step):
        init_name = step.get("name"); init_map = self.profile.get("initializations", {});
        relative_script_path = init_map.get(init_name)
        if not relative_script_path: return False, f"未在Profile中找到名为 '{init_name}' 的初始化脚本"
        return self._run_script_file(relative_script_path)
    def _run_script_file(self, relative_script_path):
        profile_root = self.profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        executor = ScriptExecutor(self.serial_worker); executor.log_message.connect(self.log_message)
        try:
            with open(absolute_script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
            success, msg = executor._parse_and_execute(lines); QThread.msleep(50)
            return success, msg
        except Exception as e: return False, str(e)
    def stop(self): self.is_running = False