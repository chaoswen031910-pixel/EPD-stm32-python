import serial
import serial.tools.list_ports
from PyQt5.QtCore import QObject, pyqtSignal

class DeviceScanner(QObject):
    device_found = pyqtSignal(str, list)
    def __init__(self): super().__init__()
    def _build_frame(self, command, data=b''):
        data_len = len(data); len_h, len_l = (data_len >> 8) & 0xFF, data_len & 0xFF; frame = bytearray([0xAA, command, len_h, len_l]); frame.extend(data); checksum = 0
        for byte in frame: checksum ^= byte
        frame.append(checksum); return bytes(frame)
    def run(self):
        ports = serial.tools.list_ports.comports(); all_port_names = [p.device for p in ports]; found_port = None
        identify_frame = self._build_frame(0xF0); expected_response = b"EPD_BOARD_V1.0"
        for port_info in ports:
            port_name = port_info.device
            try:
                with serial.Serial(port_name, 115200, timeout=0.2) as ser:
                    ser.write(identify_frame); response = ser.readline()
                    if expected_response in response: found_port = port_name; break
            except (OSError, serial.SerialException): continue
        self.device_found.emit(found_port, all_port_names)