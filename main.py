# 文件: main.py

import sys
from PyQt5 import QtWidgets
from main_window import MainWindow
import utils

def main():
    app = QtWidgets.QApplication(sys.argv)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()