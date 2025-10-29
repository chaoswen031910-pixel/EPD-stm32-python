import serial
import time
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from utils import log_message

class SerialWorker(QObject):
    data_received = pyqtSignal(bytes)
    error_occurred = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, port, baud):
        super().__init__()
        self.port = port
        self.baud = baud
        self.ser = None
        self.alive = True

    def run(self):
        """这个函数将在QThread中安全地运行"""
        try:
            self.ser = serial.Serial(
                self.port,
                self.baud,
                timeout=0.1,
                dsrdtr=False,
                rtscts=False,
                xonxoff=False
            )
            
            # 关键改动：打开端口后，立即手动将RTS和DTR线设置为低电平
            self.ser.rts = False
            self.ser.dtr = False

            log_message(f"[INFO] 串口线程启动: {self.port}")
        except Exception as e:
            self.error_occurred.emit(str(e))
            return

        while self.alive:
            if not self.ser or not self.ser.is_open:
                break
            try:
                num_bytes = self.ser.in_waiting
                if num_bytes > 0:
                    data = self.ser.read(num_bytes)
                    if data:
                        self.data_received.emit(data)
            except Exception as e:
                self.error_occurred.emit(f"串口读取错误: {e}")
                break
            time.sleep(0.02)

        if self.ser and self.ser.is_open:
            self.ser.close()
        
        self.finished.emit()
        log_message("[INFO] 串口线程已停止。")

    def stop(self):
        """请求线程停止"""
        self.alive = False

    @pyqtSlot(bytes)
    def write(self, data):
        """提供一个安全的、可以被跨线程调用的写数据方法"""
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(data)
                self.ser.flush()
                hex_text = ' '.join(f'{b:02X}' for b in data)
                log_message(f"[TX] {hex_text}")
            except Exception as e:
                self.error_occurred.emit(f"串口写入错误: {e}")