import sys
import os
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QEventLoop, QTimer

# 导入 ScriptExecutor，它在父目录中
# 我们需要确保 Python 能找到它
try:
    from services.script_executor import ScriptExecutor
except ImportError:
    # 如果直接运行或导入时找不到，则动态添加父目录
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from services.script_executor import ScriptExecutor

class DisplayWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str, bool)
    _response_signal = pyqtSignal(bool)
    DATA_PLACEHOLDER = "SEND_IMAGE_DATA"

    def __init__(self, serial_worker, script_path, data_generator_func, task_name, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.script_path = script_path
        self.data_generator = data_generator_func
        self.task_name = task_name
        self.is_running = True
        self.ack_result = False

    def _on_data_received(self, data):
        if b'\xcc' in data: self.ack_result = True; self._response_signal.emit(True)
        elif b'\xee' in data: self.ack_result = False; self._response_signal.emit(False)

    def _wait_for_ack(self, timeout=4000):
        self.ack_result = False; loop = QEventLoop(); self._response_signal.connect(loop.quit); QTimer.singleShot(timeout, loop.quit); loop.exec_(); self._response_signal.disconnect(loop.quit); return self.ack_result

    def _build_frame(self, command, data=b''):
        data_len = len(data); len_h, len_l = (data_len >> 8) & 0xFF, data_len & 0xFF; frame = bytearray([0xAA, command, len_h, len_l]); frame.extend(data); checksum = 0
        for byte in frame: checksum ^= byte
        frame.append(checksum); return bytes(frame)

    def run(self):
        self.serial_worker.data_received.connect(self._on_data_received)
        try:
            with open(self.script_path, 'r', encoding='utf-8') as f: script_lines = f.readlines()
            placeholder_indices = [i for i, line in enumerate(script_lines) if self.DATA_PLACEHOLDER in line]
            data_chunks = self.data_generator()
            if not isinstance(data_chunks, (list, tuple)):
                data_chunks = [data_chunks] 
            if placeholder_indices and len(data_chunks) != len(placeholder_indices):
                self.finished.emit(False, f"脚本需要 {len(placeholder_indices)} 份图像数据, 但只生成了 {len(data_chunks)} 份")
                return
            script_parts = []
            last_index = 0
            for ph_index in placeholder_indices:
                script_parts.append("".join(script_lines[last_index:ph_index]))
                last_index = ph_index + 1
            script_parts.append("".join(script_lines[last_index:]))
            total_all_data_size = sum(len(d) for d in data_chunks if d)
            total_bytes_sent = 0
            for i, part in enumerate(script_parts):
                if not self.is_running: self.finished.emit(False, "任务被用户取消"); return
                if part.strip():
                    executor = ScriptExecutor(self.serial_worker)
                    executor.log_message.connect(lambda msg, is_err: self.log_message.emit(msg, is_err))
                    success, message = executor.execute_script_from_string(part)
                    if not success:
                        self.finished.emit(False, f"执行脚本第 {i+1} 部分失败: {message}"); return
                if i < len(data_chunks):
                    display_data = data_chunks[i]
                    if display_data is None: self.finished.emit(False, f"第 {i+1} 份图像数据生成失败"); return
                    self.log_message.emit(f"[INFO] 正在发送第 {i+1}/{len(data_chunks)} 份数据 ({len(display_data)} 字节)...", False)
                    chunk_size, bytes_sent = 2048, 0
                    while bytes_sent < len(display_data):
                        if not self.is_running: self.finished.emit(False, "任务被用户取消"); return
                        chunk = display_data[bytes_sent : bytes_sent + chunk_size]
                        frame = self._build_frame(0x03, chunk)
                        self.serial_worker.write(frame)
                        if not self._wait_for_ack():
                            self.finished.emit(False, f"发送数据块 {i+1} 失败: 在偏移量 {bytes_sent} 处无应答"); return
                        bytes_sent += len(chunk)
                        current_total_sent = total_bytes_sent + bytes_sent
                        if total_all_data_size > 0:
                            self.progress.emit(int(current_total_sent * 100 / total_all_data_size))
                    total_bytes_sent += len(display_data)
            self.finished.emit(True, f"{self.task_name} 成功")
        except FileNotFoundError: self.finished.emit(False, f"显示脚本未找到: {self.script_path}")
        except Exception as e: self.finished.emit(False, f"执行显示任务时发生未知错误: {e}")
        finally:
            if self.serial_worker:
                try: self.serial_worker.data_received.disconnect(self._on_data_received)
                except (TypeError, RuntimeError): pass
    
    def stop(self):
        self.is_running = False