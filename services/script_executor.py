import os
import time
from PyQt5.QtCore import QObject, pyqtSignal, QEventLoop, QTimer

# --- 常量定义 ---
FRAME_HEADER = 0xAA
CMD_RESET = 0x01
CMD_SPI_CMD = 0x02
CMD_SPI_DATA = 0x03
CMD_DELAY_MS = 0x04
CMD_WAIT_BUSY_GENERIC = 0x05 # 通用
CMD_WAIT_BUSY_SSD = 0x06     # SSD专用
RSP_ACK = 0xCC
RSP_NACK = 0xEE

class ScriptExecutor(QObject):
    log_message = pyqtSignal(str, bool)
    _response_signal = pyqtSignal(bool)

    def __init__(self, serial_worker):
        super().__init__()
        self.serial_worker = serial_worker
        self.is_running = True
        self.ack_result = False
        self.serial_worker.data_received.connect(self._on_data_received)

    def _on_data_received(self, data):
        if RSP_ACK in data: self.ack_result = True; self._response_signal.emit(True)
        elif RSP_NACK in data: self.ack_result = False; self._response_signal.emit(False)

    def _wait_for_ack(self, timeout=2000):
        self.ack_result = False; loop = QEventLoop()
        self._response_signal.connect(loop.quit)
        QTimer.singleShot(timeout, loop.quit); loop.exec_()
        self._response_signal.disconnect(loop.quit)
        return self.ack_result

    def _build_frame(self, command, data=b''):
        data_len = len(data); len_h = (data_len >> 8) & 0xFF; len_l = data_len & 0xFF
        frame = bytearray([FRAME_HEADER, command, len_h, len_l]); frame.extend(data)
        checksum = 0
        for byte in frame: checksum ^= byte
        frame.append(checksum); return bytes(frame)

    def _parse_and_execute(self, lines, lut_data_bytes=None):
        for line_num, line in enumerate(lines, 1):
            if not self.is_running: return False, "任务被中途停止"
            
            line_content = line.split('#')[0].strip()
            if not line_content: continue

            parts = line_content.replace(',', ' ').split()
            instruction = parts[0].upper()
            args = parts[1:]
            
            frame = None; error_msg = None
            default_timeout = 8000
            
            try:
                if instruction == "RESET": frame = self._build_frame(CMD_RESET)
                elif instruction == "CMD": frame = self._build_frame(CMD_SPI_CMD, bytes([int(arg, 16) for arg in args]))
                elif instruction == "DATA": frame = self._build_frame(CMD_SPI_DATA, bytes([int(arg, 16) for arg in args]))
                elif instruction == "DELAY": time.sleep(int(args[0]) / 1000.0); continue
                
                elif instruction in ("WAIT_BUSY", "WAIT_BUSY_SSD"):
                    command_code = CMD_WAIT_BUSY_GENERIC if instruction == "WAIT_BUSY" else CMD_WAIT_BUSY_SSD
                    frame = self._build_frame(command_code)
                    if args: # 如果WAIT_BUSY后面带了参数, 就把它作为超时时间
                        default_timeout = int(args[0])

                elif instruction == "SEND_LUT_DATA_CHUNK":
                    if lut_data_bytes is None: return False, f"脚本第{line_num}行: SEND_LUT_DATA_CHUNK 指令需要LUT数据，但未提供。"
                    start, end = int(args[0]), int(args[1])
                    frame = self._build_frame(CMD_SPI_DATA, lut_data_bytes[start:end])
                else: error_msg = f"脚本第{line_num}行: 未知指令 '{instruction}'"
            except Exception as e:
                error_msg = f"脚本第{line_num}行: 指令参数错误 '{line_content}' - {e}"

            if error_msg: return False, error_msg

            if frame:
                self.serial_worker.write(frame)
                if not self._wait_for_ack(default_timeout):
                    return False, f"脚本第{line_num}行: {instruction} 指令无应答或超时({default_timeout}ms)"
        
        return True, "脚本部分执行成功"

    def run_script(self, script_path, lut_data_bytes=None):
        self.is_running = True
        try:
            with open(script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
            success, message = self._parse_and_execute(lines, lut_data_bytes)
            if success:
                self.log_message.emit(f"脚本 '{os.path.basename(script_path)}' 执行成功。", False)
            else:
                self.log_message.emit(f"执行脚本 '{os.path.basename(script_path)}' 时失败: {message}", True)
        except FileNotFoundError:
            self.log_message.emit(f"脚本文件未找到: {script_path}", True)

    def execute_script_from_string(self, script_content):
        self.is_running = True
        lines = [line.strip() for line in script_content.splitlines() if line.strip()]
        return self._parse_and_execute(lines)

    def stop_all_tasks(self): self.is_running = False

    def __del__(self):
        try: self.serial_worker.data_received.disconnect(self._on_data_received)
        except (TypeError, RuntimeError): pass