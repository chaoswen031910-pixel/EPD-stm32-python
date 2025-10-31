from PyQt5 import QtWidgets

class CodeGenOptionsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("选择要生成的代码部分")
        self.layout = QtWidgets.QVBoxLayout(self)
        self.options = {
            'reset': QtWidgets.QCheckBox("硬件复位 (Hardware_Reset)"),
            'init': QtWidgets.QCheckBox("IC初始化 (..._Init)"),
            'lut': QtWidgets.QCheckBox("波形加载 (Lut_Load)"),
            'display': QtWidgets.QCheckBox("刷图函数 (Dis_Pic, Display_Update)"),
            'sleep': QtWidgets.QCheckBox("休眠函数 (EPD_Sleep)"),
        }
        self.options['init'].setChecked(True)
        group_box = QtWidgets.QGroupBox("勾选需要生成的函数:")
        group_layout = QtWidgets.QVBoxLayout(group_box)
        for key in self.options:
            group_layout.addWidget(self.options[key])
        self.layout.addWidget(group_box)
        button_layout = QtWidgets.QHBoxLayout()
        select_all_btn = QtWidgets.QPushButton("全选")
        select_all_btn.clicked.connect(self.select_all)
        self.generate_btn = QtWidgets.QPushButton("生成代码")
        self.generate_btn.clicked.connect(self.accept)
        button_layout.addWidget(select_all_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.generate_btn)
        self.layout.addLayout(button_layout)

    def select_all(self):
        for checkbox in self.options.values():
            checkbox.setChecked(True)

    def get_selected_parts(self):
        return [key for key, checkbox in self.options.items() if checkbox.isChecked()]