import sys
import os
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QEventLoop, QTimer

# 导入 ScriptExecutor，它在父目录中
try:
    from script_executor import ScriptExecutor
except ImportError:
    # 如果直接运行或导入时找不到，则动态添加父目录
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from script_executor import ScriptExecutor

class MultiImageDisplayWorker(QObject):
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int, int, str, int)
    log_message = pyqtSignal(str, bool)
    _response_signal = pyqtSignal(bool)

    def __init__(self, serial_worker, script_path, image_paths_func, process_func, task_name, 
                 is_looping, interval_ms, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.script_path = script_path
        self.get_image_paths = image_paths_func
        self.process_image_func = process_func
        self.task_name = task_name
        self.is_looping = is_looping
        self.interval_ms = interval_ms
        self.is_running = True
        self.is_paused = False
        self.ack_result = False

    def pause(self): self.is_paused = True
    def resume(self): self.is_paused = False

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
            while self.is_running:
                image_paths = self.get_image_paths()
                total_images = len(image_paths)
                if total_images == 0:
                    self.finished.emit(False, "发送队列为空。"); return
                with open(self.script_path, 'r', encoding='utf-8') as f: script_lines = f.readlines()
                DATA_PLACEHOLDER = "SEND_IMAGE_DATA"
                placeholder_indices = [i for i, line in enumerate(script_lines) if DATA_PLACEHOLDER in line]
                if not placeholder_indices:
                    self.finished.emit(False, f"脚本中未找到占位符。"); return
                script_parts = []
                last_index = 0
                for ph_index in placeholder_indices:
                    script_parts.append("".join(script_lines[last_index:ph_index]))
                    last_index = ph_index + 1
                script_parts.append("".join(script_lines[last_index:]))
                for index, image_path in enumerate(image_paths):
                    while self.is_paused:
                        if not self.is_running: break
                        QThread.msleep(100)
                    if not self.is_running: self.finished.emit(False, "任务被用户取消"); return
                    self.progress.emit(index + 1, total_images, os.path.basename(image_path), 0)
                    self.log_message.emit(f"--- 开始处理第 {index + 1}/{total_images} 张图片: {os.path.basename(image_path)} ---", False)
                    raw_display_data = self.process_image_func(image_path)
                    if raw_display_data is None:
                        self.log_message.emit(f"[ERROR] 处理图片失败，跳过。", True)
                        QThread.msleep(self.interval_ms)
                        continue
                    data_chunks = raw_display_data if isinstance(raw_display_data, (list, tuple)) else [raw_display_data]
                    if len(data_chunks) != len(placeholder_indices):
                        self.log_message.emit(f"[ERROR] 图片与脚本数据块数量不匹配，跳过。", True)
                        QThread.msleep(self.interval_ms)
                        continue
                    total_bytes_to_send = sum(len(d) for d in data_chunks)
                    total_bytes_sent_for_image = 0
                    for i, part in enumerate(script_parts):
                        while self.is_paused:
                            if not self.is_running: break
                            QThread.msleep(100)
                        if not self.is_running: self.finished.emit(False, "任务被用户取消"); return
                        if part.strip():
                            executor = ScriptExecutor(self.serial_worker)
                            executor.log_message.connect(self.log_message)
                            success, message = executor.execute_script_from_string(part)
                            if not success: self.finished.emit(False, f"执行脚本失败于图片 {index + 1}: {message}"); return
                        if i < len(data_chunks):
                            chunk_to_send = data_chunks[i]
                            chunk_size, bytes_sent_for_chunk = 2048, 0
                            while bytes_sent_for_chunk < len(chunk_to_send):
                                while self.is_paused:
                                    if not self.is_running: break
                                    QThread.msleep(100)
                                if not self.is_running: self.finished.emit(False, "任务被用户取消"); return
                                chunk = chunk_to_send[bytes_sent_for_chunk : bytes_sent_for_chunk + chunk_size]
                                frame = self._build_frame(0x03, chunk)
                                self.serial_worker.write(frame)
                                if not self._wait_for_ack():
                                    self.finished.emit(False, f"发送数据失败于图片 {index+1}，无应答"); return
                                bytes_sent_for_chunk += len(chunk)
                                current_total_sent = total_bytes_sent_for_image + bytes_sent_for_chunk
                                if total_bytes_to_send > 0:
                                    self.progress.emit(index + 1, total_images, os.path.basename(image_path), int(current_total_sent * 100 / total_bytes_to_send))
                            total_bytes_sent_for_image += len(chunk_to_send)
                    self.log_message.emit(f"第 {index + 1}/{total_images} 张图片发送完毕。", False)
                    self.log_message.emit(f"等待 {self.interval_ms} 毫秒...", False)
                    QThread.msleep(self.interval_ms)
                if not self.is_looping: break
            self.finished.emit(True, "任务执行完毕。")
        except Exception as e:
            self.finished.emit(False, f"执行多图发送任务时发生未知错误: {e}")
        finally:
            if self.serial_worker and hasattr(self.serial_worker, 'data_received'):
                try: self.serial_worker.data_received.disconnect(self._on_data_received)
                except (TypeError, RuntimeError): pass

    def stop(self):
        self.is_running = False
        self.is_paused = False