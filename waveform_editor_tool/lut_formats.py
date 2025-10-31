from PyQt5 import QtWidgets, QtCore, QtGui
from .ui_components import FrameInput, ColorBlockWidget 

class BaseLutFormatHandler:
    """
    所有LUT格式处理器的基类，定义了必须实现的接口。
    """
    def __init__(self, profile):
        self.profile = profile
        self.voltage_map = {"G": 0b00, "H": 0b01, "L": 0b10}
        self.widgets = {} # 初始化为空字典，由子类填充

    def build_ui(self, grid_layout: QtWidgets.QGridLayout):
        raise NotImplementedError

    def compile(self) -> bytes:
        raise NotImplementedError

    def populate(self, lut_data: bytes):
        raise NotImplementedError

    def format_to_c_array(self, data_bytes: bytes, var_name="gLutData") -> str:
        """将字节数据格式化为完整的C语言数组字符串"""
        lines = [f"const uint8_t {var_name}[{len(data_bytes)}] = {{"]
        for i in range(0, len(data_bytes), 16):
            chunk = data_bytes[i:i+16]
            hex_string = ", ".join([f"0x{b:02X}" for b in chunk])
            lines.append(f"    {hex_string},")
        lines.append("};")
        return "\n".join(lines)

# ==============================================================================
#  处理器实现 1: IC_6x7 格式
# ==============================================================================
class IC_6x7_Handler(BaseLutFormatHandler):
    NUM_GROUPS = 6
    BYTES_PER_GROUP = 7
    NUM_LUT_PARTS = 5
    TP_LABELS = ["// VCOM", "// LUT_WW", "// LUT_BW", "// LUT_WB", "// LUT_BB"]
    
    def __init__(self, profile):
        super().__init__(profile)
        self.widgets = {
            "g_rp": [], "s_rt1": [], "s_rt2": [], "frame": [],
            "tp_vcom": [], "tp_ww": [], "tp_bw": [], "tp_wb": [], "tp_bb": []
        }

    def build_ui(self, grid: QtWidgets.QGridLayout):
        header_font = QtGui.QFont(); header_font.setBold(True)
        for i in range(self.NUM_GROUPS):
            grid.addWidget(QtWidgets.QLabel(f"Group {i+1}", font=header_font, alignment=QtCore.Qt.AlignCenter), 0, 2 + i * 5, 1, 4)
            if i < self.NUM_GROUPS - 1: grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), 0, 2 + i * 5 + 4, 11, 1)
        for i in range(self.NUM_GROUPS):
            for j, sub_header in enumerate(["S1_1", "S1_2", "S2_1", "S2_2"]):
                grid.addWidget(QtWidgets.QLabel(sub_header, alignment=QtCore.Qt.AlignCenter), 1, 2 + i * 5 + j)
        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 2, 0, 1, grid.columnCount())
        shared_params = ["G_RP", "S_RT", "Frame(帧数)"]
        for row, label_text in enumerate(shared_params, 3):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
        for i in range(self.NUM_GROUPS):
            g_rp = FrameInput(); self.widgets["g_rp"].append(g_rp)
            grid.addWidget(g_rp, 3, 2 + i * 5, 1, 4, alignment=QtCore.Qt.AlignCenter)
            s_rt1 = FrameInput(); self.widgets["s_rt1"].append(s_rt1)
            grid.addWidget(s_rt1, 4, 2 + i * 5, 1, 2, alignment=QtCore.Qt.AlignCenter)
            s_rt2 = FrameInput(); self.widgets["s_rt2"].append(s_rt2)
            grid.addWidget(s_rt2, 4, 4 + i * 5, 1, 2, alignment=QtCore.Qt.AlignCenter)
            for j in range(4):
                frame = FrameInput(); self.widgets["frame"].append(frame)
                grid.addWidget(frame, 5, 2 + i * 5 + j, alignment=QtCore.Qt.AlignCenter)
        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 6, 0, 1, grid.columnCount())
        
        tp_labels = ["VCOM", "LUT_WW", "LUT_BW", "LUT_WB", "LUT_BB"]
        tp_keys = ["tp_vcom", "tp_ww", "tp_bw", "tp_wb", "tp_bb"]

        for row, (label_text, key) in enumerate(zip(tp_labels, tp_keys), 7):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
            for i in range(self.NUM_GROUPS * 4):
                group_index = i // 4; sub_index = i % 4
                widget = ColorBlockWidget()
                self.widgets[key].append(widget)
                grid.addWidget(widget, row, 2 + group_index * 5 + sub_index, alignment=QtCore.Qt.AlignCenter)
    
    def compile(self) -> bytes:
        g_rps = [int(inp.text() or 0) for inp in self.widgets["g_rp"]]
        s_rt1s = [int(inp.text() or 0) for inp in self.widgets["s_rt1"]]
        s_rt2s = [int(inp.text() or 0) for inp in self.widgets["s_rt2"]]
        frames = [int(inp.text() or 0) for inp in self.widgets["frame"]]
        final_bytes = bytearray()

        tp_keys = ["tp_vcom", "tp_ww", "tp_bw", "tp_wb", "tp_bb"]
        for key in tp_keys:
            tp_list = self.widgets[key]
            part_tps = [self.voltage_map[widget.getState()] for widget in tp_list]
            for i in range(self.NUM_GROUPS):
                g_rp, s_rt1, s_rt2 = g_rps[i], s_rt1s[i], s_rt2s[i]
                frame_s1_1, frame_s1_2 = frames[i*4 + 0], frames[i*4 + 1]
                frame_s2_1, frame_s2_2 = frames[i*4 + 2], frames[i*4 + 3]
                tp_s1_1, tp_s1_2 = part_tps[i*4 + 0], part_tps[i*4 + 1]
                tp_s2_1, tp_s2_2 = part_tps[i*4 + 2], part_tps[i*4 + 3]
                byte1, byte6, byte7 = g_rp, s_rt1, s_rt2
                byte2 = (tp_s1_1 << 6) | (frame_s1_1 & 0x3F)
                byte3 = (tp_s1_2 << 6) | (frame_s1_2 & 0x3F)
                byte4 = (tp_s2_1 << 6) | (frame_s2_1 & 0x3F)
                byte5 = (tp_s2_2 << 6) | (frame_s2_2 & 0x3F)
                final_bytes.extend([byte1, byte2, byte3, byte4, byte5, byte6, byte7])
        return bytes(final_bytes)
    
    def populate(self, lut_data: bytes):
        expected_len = self.NUM_GROUPS * self.BYTES_PER_GROUP * self.NUM_LUT_PARTS
        if len(lut_data) != expected_len:
            raise ValueError(f"Invalid LUT data length for 6x7 format. Expected {expected_len}, got {len(lut_data)}")
        reverse_voltage_map = {v: k for k, v in self.voltage_map.items()}
        
        tp_keys = ["tp_vcom", "tp_ww", "tp_bw", "tp_wb", "tp_bb"]
        for part_idx, key in enumerate(tp_keys):
            part_data = lut_data[part_idx * 42 : (part_idx + 1) * 42]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * 7 : (i + 1) * 7]
                g_rp, byte2, byte3, byte4, byte5, s_rt1, s_rt2 = group_data
                tp_s1_1, frame_s1_1 = (byte2 >> 6) & 0b11, byte2 & 0x3F
                tp_s1_2, frame_s1_2 = (byte3 >> 6) & 0b11, byte3 & 0x3F
                tp_s2_1, frame_s2_1 = (byte4 >> 6) & 0b11, byte4 & 0x3F
                tp_s2_2, frame_s2_2 = (byte5 >> 6) & 0b11, byte5 & 0x3F
                if part_idx == 0:
                    self.widgets["g_rp"][i].setText(str(g_rp))
                    self.widgets["s_rt1"][i].setText(str(s_rt1))
                    self.widgets["s_rt2"][i].setText(str(s_rt2))
                    self.widgets["frame"][i*4 + 0].setText(str(frame_s1_1))
                    self.widgets["frame"][i*4 + 1].setText(str(frame_s1_2))
                    self.widgets["frame"][i*4 + 2].setText(str(frame_s2_1))
                    self.widgets["frame"][i*4 + 3].setText(str(frame_s2_2))
                tp_widgets = self.widgets[key]
                tp_widgets[i*4 + 0].setState(reverse_voltage_map.get(tp_s1_1, 'G'))
                tp_widgets[i*4 + 1].setState(reverse_voltage_map.get(tp_s1_2, 'G'))
                tp_widgets[i*4 + 2].setState(reverse_voltage_map.get(tp_s2_1, 'G'))
                tp_widgets[i*4 + 3].setState(reverse_voltage_map.get(tp_s2_2, 'G'))
    
    def format_to_c_array(self, data_bytes: bytes, var_name="gLutData_6x7") -> str:
        lines = [f"const uint8_t {var_name}[{len(data_bytes)}] = {{"]
        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, part_name in enumerate(self.TP_LABELS):
            lines.append(f"    {part_name}")
            part_data = data_bytes[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                hex_string = ",\t".join([f"0x{b:02X}" for b in group_data])
                lines.append(f"    {hex_string},")
        lines.append("};")
        return "\n".join(lines)

# ==============================================================================
#  处理器实现 2: IC_7x8 格式
# ==============================================================================
class IC_7x8_Handler(BaseLutFormatHandler):
    NUM_GROUPS = 7
    BYTES_PER_GROUP = 8
    NUM_LUT_PARTS = 5
    TP_LABELS = ["// VCOM", "// LUT_BB", "// LUT_WB", "// LUT_BW", "// LUT_WW"]
    
    def __init__(self, profile):
        super().__init__(profile)
        self.widgets = {
            "g_rp": [], "s_rt1": [], "s_rt2": [], "frame": [],
            "tp_vcom": [], "tp_bb": [], "tp_wb": [], "tp_bw": [], "tp_ww": []
        }

    def build_ui(self, grid: QtWidgets.QGridLayout):
        header_font = QtGui.QFont(); header_font.setBold(True)
        for i in range(self.NUM_GROUPS):
            grid.addWidget(QtWidgets.QLabel(f"Group {i+1}", font=header_font, alignment=QtCore.Qt.AlignCenter), 0, 2 + i * 5, 1, 4)
            if i < self.NUM_GROUPS - 1: grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), 0, 2 + i * 5 + 4, 11, 1)
        for i in range(self.NUM_GROUPS):
            for j, sub_header in enumerate(["S1_1", "S1_2", "S2_1", "S2_2"]):
                grid.addWidget(QtWidgets.QLabel(sub_header, alignment=QtCore.Qt.AlignCenter), 1, 2 + i * 5 + j)
        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 2, 0, 1, grid.columnCount())
        shared_params = ["G_RP", "S_RT", "Frame(帧数)"]
        for row, label_text in enumerate(shared_params, 3):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
        for i in range(self.NUM_GROUPS):
            g_rp = FrameInput(); self.widgets["g_rp"].append(g_rp)
            grid.addWidget(g_rp, 3, 2 + i * 5, 1, 4, alignment=QtCore.Qt.AlignCenter)
            s_rt1 = FrameInput(); self.widgets["s_rt1"].append(s_rt1)
            grid.addWidget(s_rt1, 4, 2 + i * 5, 1, 2, alignment=QtCore.Qt.AlignCenter)
            s_rt2 = FrameInput(); self.widgets["s_rt2"].append(s_rt2)
            grid.addWidget(s_rt2, 4, 4 + i * 5, 1, 2, alignment=QtCore.Qt.AlignCenter)
            for j in range(4):
                frame = FrameInput(); self.widgets["frame"].append(frame)
                grid.addWidget(frame, 5, 2 + i * 5 + j, alignment=QtCore.Qt.AlignCenter)
        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 6, 0, 1, grid.columnCount())
        
        tp_labels = ["VCOM", "Lut_BB", "Lut_WB", "Lut_BW", "Lut_WW"]
        tp_keys = ["tp_vcom", "tp_bb", "tp_wb", "tp_bw", "tp_ww"]

        for row, (label_text, key) in enumerate(zip(tp_labels, tp_keys), 7):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
            for i in range(self.NUM_GROUPS * 4):
                group_index = i // 4; sub_index = i % 4
                widget = ColorBlockWidget()
                self.widgets[key].append(widget)
                grid.addWidget(widget, row, 2 + group_index * 5 + sub_index, alignment=QtCore.Qt.AlignCenter)

    def compile(self) -> bytes:
        g_rps = [int(inp.text() or 0) for inp in self.widgets["g_rp"]]
        s_rt1s = [int(inp.text() or 0) for inp in self.widgets["s_rt1"]]
        s_rt2s = [int(inp.text() or 0) for inp in self.widgets["s_rt2"]]
        frames = [int(inp.text() or 0) for inp in self.widgets["frame"]]
        final_bytes = bytearray()
        
        hw_order_keys = ["tp_vcom", "tp_bb", "tp_wb", "tp_bw", "tp_ww"]

        for key in hw_order_keys:
            part_tps_vals = [self.voltage_map[widget.getState()] for widget in self.widgets[key]]
            
            for i in range(self.NUM_GROUPS):
                tp1 = part_tps_vals[i*4 + 0]
                tp2 = part_tps_vals[i*4 + 1]
                tp3 = part_tps_vals[i*4 + 2]
                tp4 = part_tps_vals[i*4 + 3]
                
                packed_tp = (tp1 << 6) | (tp2 << 4) | (tp3 << 2) | tp4

                byte1 = g_rps[i]
                byte2 = packed_tp
                byte3 = frames[i*4 + 0]
                byte4 = frames[i*4 + 1]
                byte5 = s_rt1s[i]
                byte6 = frames[i*4 + 2]
                byte7 = frames[i*4 + 3]
                byte8 = s_rt2s[i]
                final_bytes.extend([byte1, byte2, byte3, byte4, byte5, byte6, byte7, byte8])
        return bytes(final_bytes)

    def populate(self, lut_data: bytes):
        expected_len = self.NUM_GROUPS * self.BYTES_PER_GROUP * self.NUM_LUT_PARTS
        if len(lut_data) != expected_len:
            raise ValueError(f"Invalid LUT data length for 7x8 format. Expected {expected_len}, got {len(lut_data)}")

        reverse_voltage_map = {v: k for k, v in self.voltage_map.items()}
        
        hw_order_keys = ["tp_vcom", "tp_bb", "tp_wb", "tp_bw", "tp_ww"]

        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, key in enumerate(hw_order_keys):
            part_data = lut_data[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                
                g_rp, packed_tp, f1, f2, s_rt1, f3, f4, s_rt2 = group_data
                
                if part_idx == 0:
                    self.widgets["g_rp"][i].setText(str(g_rp))
                    self.widgets["s_rt1"][i].setText(str(s_rt1))
                    self.widgets["s_rt2"][i].setText(str(s_rt2))
                    self.widgets["frame"][i*4+0].setText(str(f1))
                    self.widgets["frame"][i*4+1].setText(str(f2))
                    self.widgets["frame"][i*4+2].setText(str(f3))
                    self.widgets["frame"][i*4+3].setText(str(f4))

                tp_widgets = self.widgets[key]
                tp1 = (packed_tp >> 6) & 0b11
                tp2 = (packed_tp >> 4) & 0b11
                tp3 = (packed_tp >> 2) & 0b11
                tp4 = packed_tp & 0b11
                tp_widgets[i*4+0].setState(reverse_voltage_map.get(tp1, 'G'))
                tp_widgets[i*4+1].setState(reverse_voltage_map.get(tp2, 'G'))
                tp_widgets[i*4+2].setState(reverse_voltage_map.get(tp3, 'G'))
                tp_widgets[i*4+3].setState(reverse_voltage_map.get(tp4, 'G'))

    def format_to_c_array(self, data_bytes: bytes, var_name="gLutData_7x8") -> str:
        lines = [f"const uint8_t {var_name}[{len(data_bytes)}] = {{"]
        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, part_name in enumerate(self.TP_LABELS):
            lines.append(f"    {part_name}")
            part_data = data_bytes[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                hex_string = ",\t".join([f"0x{b:02X}" for b in group_data])
                lines.append(f"    {hex_string}, // Group {i+1}")
        lines.append("};")
        return "\n".join(lines)

# ==============================================================================
#  处理器实现 3: IC_6x6 格式
# ==============================================================================
class IC_6x6_Handler(BaseLutFormatHandler):
    NUM_GROUPS = 6
    BYTES_PER_GROUP = 6
    NUM_LUT_PARTS = 5
    TP_LABELS = ["// VCOM", "// LUT_WW", "// LUT_BW", "// LUT_WB", "// LUT_BB"]

    def __init__(self, profile):
        super().__init__(profile)
        self.widgets = {
            "g_rp": [], "frame": [],
            "tp_vcom": [], "tp_bb": [], "tp_wb": [], "tp_bw": [], "tp_ww": []
        }

    def build_ui(self, grid: QtWidgets.QGridLayout):
        header_font = QtGui.QFont(); header_font.setBold(True)
        for i in range(self.NUM_GROUPS):
            grid.addWidget(QtWidgets.QLabel(f"Group {i+1}", font=header_font, alignment=QtCore.Qt.AlignCenter), 0, 2 + i * 5, 1, 4)
            if i < self.NUM_GROUPS - 1: grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), 0, 2 + i * 5 + 4, 10, 1)
        for i in range(self.NUM_GROUPS):
            for j, sub_header in enumerate(["S1_1", "S1_2", "S2_1", "S2_2"]):
                grid.addWidget(QtWidgets.QLabel(sub_header, alignment=QtCore.Qt.AlignCenter), 1, 2 + i * 5 + j)
        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 2, 0, 1, grid.columnCount())
        
        shared_params = ["G_RP", "Frame(帧数)"]
        for row, label_text in enumerate(shared_params, 3):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
            
        for i in range(self.NUM_GROUPS):
            g_rp = FrameInput(); self.widgets["g_rp"].append(g_rp)
            grid.addWidget(g_rp, 3, 2 + i * 5, 1, 4, alignment=QtCore.Qt.AlignCenter)
            for j in range(4):
                frame = FrameInput(); self.widgets["frame"].append(frame)
                grid.addWidget(frame, 4, 2 + i * 5 + j, alignment=QtCore.Qt.AlignCenter)

        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 5, 0, 1, grid.columnCount())
        
        tp_labels = ["VCOM", "Lut_WW", "Lut_BW", "Lut_WB", "Lut_BB"]
        tp_keys = ["tp_vcom", "tp_ww", "tp_bw", "tp_wb", "tp_bb"]

        for row, (label_text, key) in enumerate(zip(tp_labels, tp_keys), 6):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
            for i in range(self.NUM_GROUPS * 4):
                group_index = i // 4; sub_index = i % 4
                widget = ColorBlockWidget()
                self.widgets[key].append(widget)
                grid.addWidget(widget, row, 2 + group_index * 5 + sub_index, alignment=QtCore.Qt.AlignCenter)

    def compile(self) -> bytes:
        g_rps = [int(inp.text() or 0) for inp in self.widgets["g_rp"]]
        frames = [int(inp.text() or 0) for inp in self.widgets["frame"]]
        final_bytes = bytearray()
        
        hw_order_keys = ["tp_vcom", "tp_ww", "tp_bw", "tp_wb", "tp_bb"]

        for key in hw_order_keys:
            part_tps_vals = [self.voltage_map[widget.getState()] for widget in self.widgets[key]]
            for i in range(self.NUM_GROUPS):
                tp1 = part_tps_vals[i*4 + 0]
                tp2 = part_tps_vals[i*4 + 1]
                tp3 = part_tps_vals[i*4 + 2]
                tp4 = part_tps_vals[i*4 + 3]
                
                packed_tp = (tp1 << 6) | (tp2 << 4) | (tp3 << 2) | tp4

                byte1 = packed_tp
                byte2 = frames[i*4 + 0]
                byte3 = frames[i*4 + 1]
                byte4 = frames[i*4 + 2]
                byte5 = frames[i*4 + 3]
                byte6 = g_rps[i]
                final_bytes.extend([byte1, byte2, byte3, byte4, byte5, byte6])
        return bytes(final_bytes)

    def populate(self, lut_data: bytes):
        expected_len = self.NUM_GROUPS * self.BYTES_PER_GROUP * self.NUM_LUT_PARTS
        if len(lut_data) != expected_len:
            raise ValueError(f"Invalid LUT data length for 6x6 format. Expected {expected_len}, got {len(lut_data)}")

        reverse_voltage_map = {v: k for k, v in self.voltage_map.items()}
        
        hw_order_keys = ["tp_vcom", "tp_ww", "tp_bw", "tp_wb", "tp_bb"]

        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, key in enumerate(hw_order_keys):
            part_data = lut_data[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                
                packed_tp, f1, f2, f3, f4, g_rp = group_data
                
                if part_idx == 0:
                    self.widgets["g_rp"][i].setText(str(g_rp))
                    self.widgets["frame"][i*4+0].setText(str(f1))
                    self.widgets["frame"][i*4+1].setText(str(f2))
                    self.widgets["frame"][i*4+2].setText(str(f3))
                    self.widgets["frame"][i*4+3].setText(str(f4))

                tp_widgets = self.widgets[key]
                tp1 = (packed_tp >> 6) & 0b11
                tp2 = (packed_tp >> 4) & 0b11
                tp3 = (packed_tp >> 2) & 0b11
                tp4 = packed_tp & 0b11
                tp_widgets[i*4+0].setState(reverse_voltage_map.get(tp1, 'G'))
                tp_widgets[i*4+1].setState(reverse_voltage_map.get(tp2, 'G'))
                tp_widgets[i*4+2].setState(reverse_voltage_map.get(tp3, 'G'))
                tp_widgets[i*4+3].setState(reverse_voltage_map.get(tp4, 'G'))

    def format_to_c_array(self, data_bytes: bytes, var_name="gLutData_6x6") -> str:
        lines = [f"const uint8_t {var_name}[{len(data_bytes)}] = {{"]
        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, part_name in enumerate(self.TP_LABELS):
            lines.append(f"    {part_name}")
            part_data = data_bytes[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                hex_string = ",\t".join([f"0x{b:02X}" for b in group_data])
                lines.append(f"    {hex_string}, // Group {i+1}")
        lines.append("};")
        return "\n".join(lines)

# ==============================================================================
#  处理器实现 4: IC_7x6 格式 (已修改)
# ==============================================================================
class IC_7x6_Handler(BaseLutFormatHandler):
    NUM_GROUPS = 7
    BYTES_PER_GROUP = 6
    NUM_LUT_PARTS = 5
    # 修改点 1: 更新 TP_LABELS 顺序
    TP_LABELS = ["// VCOM", "// LUT_BB", "// LUT_WB", "// LUT_BW", "// LUT_WW"]

    def __init__(self, profile):
        super().__init__(profile)
        self.widgets = {
            "g_rp": [], "frame": [],
            "tp_vcom": [], "tp_bb": [], "tp_wb": [], "tp_bw": [], "tp_ww": []
        }

    def build_ui(self, grid: QtWidgets.QGridLayout):
        header_font = QtGui.QFont(); header_font.setBold(True)
        for i in range(self.NUM_GROUPS):
            grid.addWidget(QtWidgets.QLabel(f"Group {i+1}", font=header_font, alignment=QtCore.Qt.AlignCenter), 0, 2 + i * 5, 1, 4)
            if i < self.NUM_GROUPS - 1: grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), 0, 2 + i * 5 + 4, 10, 1)
        for i in range(self.NUM_GROUPS):
            for j, sub_header in enumerate(["S1_1", "S1_2", "S2_1", "S2_2"]):
                grid.addWidget(QtWidgets.QLabel(sub_header, alignment=QtCore.Qt.AlignCenter), 1, 2 + i * 5 + j)
        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 2, 0, 1, grid.columnCount())
        
        shared_params = ["G_RP", "Frame(帧数)"]
        for row, label_text in enumerate(shared_params, 3):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
            
        for i in range(self.NUM_GROUPS):
            g_rp = FrameInput(); self.widgets["g_rp"].append(g_rp)
            grid.addWidget(g_rp, 3, 2 + i * 5, 1, 4, alignment=QtCore.Qt.AlignCenter)
            for j in range(4):
                frame = FrameInput(); self.widgets["frame"].append(frame)
                grid.addWidget(frame, 4, 2 + i * 5 + j, alignment=QtCore.Qt.AlignCenter)

        grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.HLine), 5, 0, 1, grid.columnCount())
        
        # 修改点 2: 更新UI标签和Key的顺序
        tp_labels = ["VCOM", "Lut_BB", "Lut_WB", "Lut_BW", "Lut_WW"]
        tp_keys = ["tp_vcom", "tp_bb", "tp_wb", "tp_bw", "tp_ww"]

        for row, (label_text, key) in enumerate(zip(tp_labels, tp_keys), 6):
            grid.addWidget(QtWidgets.QLabel(label_text, font=header_font, alignment=QtCore.Qt.AlignRight), row, 0)
            grid.addWidget(QtWidgets.QFrame(frameShape=QtWidgets.QFrame.VLine), row, 1)
            for i in range(self.NUM_GROUPS * 4):
                group_index = i // 4; sub_index = i % 4
                widget = ColorBlockWidget()
                self.widgets[key].append(widget)
                grid.addWidget(widget, row, 2 + group_index * 5 + sub_index, alignment=QtCore.Qt.AlignCenter)

    def compile(self) -> bytes:
        g_rps = [int(inp.text() or 0) for inp in self.widgets["g_rp"]]
        frames = [int(inp.text() or 0) for inp in self.widgets["frame"]]
        final_bytes = bytearray()
        
        # 修改点 3: 更新数据处理顺序
        hw_order_keys = ["tp_vcom", "tp_bb", "tp_wb", "tp_bw", "tp_ww"]

        for key in hw_order_keys:
            part_tps_vals = [self.voltage_map[widget.getState()] for widget in self.widgets[key]]
            for i in range(self.NUM_GROUPS):
                tp1 = part_tps_vals[i*4 + 0]
                tp2 = part_tps_vals[i*4 + 1]
                tp3 = part_tps_vals[i*4 + 2]
                tp4 = part_tps_vals[i*4 + 3]
                
                packed_tp = (tp1 << 6) | (tp2 << 4) | (tp3 << 2) | tp4

                byte1 = packed_tp
                byte2 = frames[i*4 + 0]
                byte3 = frames[i*4 + 1]
                byte4 = frames[i*4 + 2]
                byte5 = frames[i*4 + 3]
                byte6 = g_rps[i]
                final_bytes.extend([byte1, byte2, byte3, byte4, byte5, byte6])
        return bytes(final_bytes)

    def populate(self, lut_data: bytes):
        expected_len = self.NUM_GROUPS * self.BYTES_PER_GROUP * self.NUM_LUT_PARTS
        if len(lut_data) != expected_len:
            raise ValueError(f"Invalid LUT data length for 7x6 format. Expected {expected_len}, got {len(lut_data)}")

        reverse_voltage_map = {v: k for k, v in self.voltage_map.items()}
        
        # 修改点 4: 更新数据处理顺序
        hw_order_keys = ["tp_vcom", "tp_bb", "tp_wb", "tp_bw", "tp_ww"]

        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, key in enumerate(hw_order_keys):
            part_data = lut_data[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                
                packed_tp, f1, f2, f3, f4, g_rp = group_data
                
                if part_idx == 0:
                    self.widgets["g_rp"][i].setText(str(g_rp))
                    self.widgets["frame"][i*4+0].setText(str(f1))
                    self.widgets["frame"][i*4+1].setText(str(f2))
                    self.widgets["frame"][i*4+2].setText(str(f3))
                    self.widgets["frame"][i*4+3].setText(str(f4))

                tp_widgets = self.widgets[key]
                tp1 = (packed_tp >> 6) & 0b11
                tp2 = (packed_tp >> 4) & 0b11
                tp3 = (packed_tp >> 2) & 0b11
                tp4 = packed_tp & 0b11
                tp_widgets[i*4+0].setState(reverse_voltage_map.get(tp1, 'G'))
                tp_widgets[i*4+1].setState(reverse_voltage_map.get(tp2, 'G'))
                tp_widgets[i*4+2].setState(reverse_voltage_map.get(tp3, 'G'))
                tp_widgets[i*4+3].setState(reverse_voltage_map.get(tp4, 'G'))

    def format_to_c_array(self, data_bytes: bytes, var_name="gLutData_7x6") -> str:
        lines = [f"const uint8_t {var_name}[{len(data_bytes)}] = {{"]
        bytes_per_part = self.NUM_GROUPS * self.BYTES_PER_GROUP
        for part_idx, part_name in enumerate(self.TP_LABELS):
            lines.append(f"    {part_name}")
            part_data = data_bytes[part_idx * bytes_per_part : (part_idx + 1) * bytes_per_part]
            for i in range(self.NUM_GROUPS):
                group_data = part_data[i * self.BYTES_PER_GROUP : (i + 1) * self.BYTES_PER_GROUP]
                hex_string = ",\t".join([f"0x{b:02X}" for b in group_data])
                lines.append(f"    {hex_string}, // Group {i+1}")
        lines.append("};")
        return "\n".join(lines)
        
# ==============================================================================
#  处理器实现 5: IC_SSD1677 格式
# ==============================================================================
# lut_formats.py

# ==============================================================================
#  处理器实现 5: IC_SSD1677 格式 (修改为文本粘贴模式)
# ==============================================================================
class IC_SSD1677_Handler(BaseLutFormatHandler):
    def __init__(self, profile):
        super().__init__(profile)
        # 简化widgets，只需要一个文本编辑器
        self.widgets = {
            "text_editor": None
        }

    def build_ui(self, grid: QtWidgets.QGridLayout):
        """
        创建一个大的文本编辑框，用于直接粘贴C数组。
        """
        # 清理可能存在的旧控件
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        header_font = QtGui.QFont()
        header_font.setBold(True)
        
        info_label = QtWidgets.QLabel("请直接粘贴完整的C语言数组 (例如 const uint8_t lut[] = {...}; )")
        info_label.setWordWrap(True)
        
        self.widgets["text_editor"] = QtWidgets.QTextEdit()
        # 设置一个等宽字体，方便查看代码
        font = QtGui.QFont("Courier New", 10)
        self.widgets["text_editor"].setFont(font)

        grid.addWidget(info_label, 0, 0)
        grid.addWidget(self.widgets["text_editor"], 1, 0)
        grid.setRowStretch(1, 1) # 让文本框占据大部分空间

    def compile(self) -> bytes:
        """
        从文本框中解析十六进制数值，并编译成bytes。
        """
        import re
        
        editor = self.widgets.get("text_editor")
        if not editor:
            return b''

        text_content = editor.toPlainText()
        
        # 使用正则表达式查找所有 '0x' 开头的十六进制数
        hex_values = re.findall(r'0x([0-9a-fA-F]{1,2})', text_content)
        
        if not hex_values:
            # 如果没有找到，可以给用户一个提示
            QtWidgets.QMessageBox.warning(None, "解析错误", "未在文本中找到任何有效的十六进制数据 (例如 0x_ _)。")
            return b''
            
        # 将找到的十六进制字符串转换为字节
        try:
            final_bytes = bytes([int(val, 16) for val in hex_values])
            return final_bytes
        except ValueError as e:
            QtWidgets.QMessageBox.critical(None, "转换错误", f"转换十六进制数据时出错: {e}")
            return b''

    def populate(self, lut_data: bytes):
        """
        将加载的bytes数据格式化为C数组，并填充到文本框中。
        """
        editor = self.widgets.get("text_editor")
        if not editor:
            return
            
        # 复用基类中的格式化方法
        c_array_string = self.format_to_c_array(lut_data, var_name="gLutData_SSD1677")
        editor.setText(c_array_string)

    def format_to_c_array(self, data_bytes: bytes, var_name="gLutData_SSD1677") -> str:
        """
        重写此方法以提供更适合SSD1677的分段注释（如果可能）。
        如果profile中定义了lut_structure，就按结构注释。
        """
        lut_structure = self.profile.get("lut_structure")
        if not lut_structure:
            # 如果没有结构定义，就使用基类的默认格式化
            return super().format_to_c_array(data_bytes, var_name)

        lines = [f"const uint8_t {var_name}[{len(data_bytes)}] = {{"]
        
        # 为了防止段重叠，我们记录已处理的范围
        processed_indices = set()
        
        # 首先按顺序处理定义好的段
        for part_name, data_range in lut_structure.items():
            start, end = data_range
            # 检查这段是否已经作为其他段的一部分被处理过
            if start in processed_indices:
                continue
            
            part_data = data_bytes[start:end]
            
            lines.append(f"    // {part_name}")
            for i in range(0, len(part_data), 16):
                chunk = part_data[i:i+16]
                hex_string = ", ".join([f"0x{b:02X}" for b in chunk])
                lines.append(f"    {hex_string},")
                
            for i in range(start, end):
                processed_indices.add(i)

        # 检查是否有任何未被定义在structure里的数据
        if len(processed_indices) < len(data_bytes):
             lines.append(f"    // Undefined data")
             undefined_start = max(processed_indices) + 1 if processed_indices else 0
             part_data = data_bytes[undefined_start:]
             for i in range(0, len(part_data), 16):
                chunk = part_data[i:i+16]
                hex_string = ", ".join([f"0x{b:02X}" for b in chunk])
                lines.append(f"    {hex_string},")

        # 移除最后一行的逗号
        if lines[-1].endswith(','):
            lines[-1] = lines[-1][:-1]
            
        lines.append("};")
        return "\n".join(lines)
        
# ==============================================================================
#  处理器工厂: 用于根据 profile 返回对应的处理器实例
# ==============================================================================
def get_lut_handler(profile):
    format_name = profile.get("lut_format")
    if not format_name:
        if "lut_structure" in profile:
            format_name = "IC_SSD1677"
        else:
            raise ValueError(f"Profile '{profile.get('ic_name')}' 中缺少 'lut_format' 定义。")

    handler_map = {
        "IC_6x7": IC_6x7_Handler,
        "IC_7x8": IC_7x8_Handler,
        "IC_6x6": IC_6x6_Handler,
        "IC_7x6": IC_7x6_Handler,
        "IC_SSD1677": IC_SSD1677_Handler,
    }

    handler_class = handler_map.get(format_name)
    if not handler_class:
        raise NotImplementedError(f"不支持名为 '{format_name}' 的LUT格式。")
        
    return handler_class(profile)