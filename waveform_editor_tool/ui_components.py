# 文件: stm32Py/ui_components.py

from PyQt5 import QtWidgets, QtCore, QtGui

class ColorBlockWidget(QtWidgets.QLabel):
    """
    一个自定义的颜色块控件，用于显示和切换 G, H, L 三种电压电平。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 20)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.setLineWidth(1)
        self.states = ['G', 'H', 'L']
        self.colors = {'G': '#4CAF50', 'H': '#F44336', 'L': '#2196F3'}
        self.current_index = 0
        self.setState(self.states[self.current_index])
        self.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.current_index = (self.current_index + 1) % len(self.states)
            self.setState(self.states[self.current_index])
            super().mousePressEvent(event)

    def getState(self) -> str:
        return self.states[self.current_index]

    def setState(self, state: str):
        if state in self.states:
            self.current_index = self.states.index(state)
            color = self.colors.get(state, 'white')
            self.setStyleSheet(f"background-color: {color}; color: white; font-weight: bold;")
            self.setText(state)

class FrameInput(QtWidgets.QLineEdit):
    """
    一个用于输入Frame/RP/RT计数的输入框
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setValidator(QtGui.QIntValidator(0, 255))
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setFixedSize(50, 20)