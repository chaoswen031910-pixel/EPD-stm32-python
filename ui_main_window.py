from PyQt5 import QtWidgets, QtGui, QtCore

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.setWindowTitle("E-Paper-Pro Suite (EPD上位机)")
        MainWindow.resize(1250, 800)
        
        # --- [修改] 创建一个中心控件来容纳所有UI元素 ---
        central_widget = QtWidgets.QWidget(MainWindow)
        MainWindow.setCentralWidget(central_widget)
        # --- 修改结束 ---

        # 文件: ui_main_window.py

        # 1. 连接与配置区域
        connection_group = QtWidgets.QGroupBox("连接与配置")
        
        # --- [ 1. 创建顶层 垂直布局 ] ---
        # 我们使用一个 VBox 来堆叠 "串口布局" 和 "Profile布局"
        top_level_layout = QtWidgets.QVBoxLayout(connection_group)

        # --- [ 2. 串口布局 (使用 QGridLayout) ] ---
        # 我们把串口相关的控件放在第一个网格布局中
        serial_layout = QtWidgets.QGridLayout()
        
        self.port_combo = QtWidgets.QComboBox()
        self.refresh_btn = QtWidgets.QPushButton("刷新/扫描设备")
        self.baud_combo = QtWidgets.QComboBox()
        self.baud_combo.addItems(["9600", "115200", "921600"])
        self.baud_combo.setCurrentText("921600")
        self.open_btn = QtWidgets.QPushButton("连接设备")
        self.close_btn = QtWidgets.QPushButton("断开连接")
        self.close_btn.setEnabled(False)

        serial_layout.addWidget(QtWidgets.QLabel("下位机:"), 0, 0)
        serial_layout.addWidget(self.port_combo, 0, 1)
        serial_layout.addWidget(self.refresh_btn, 0, 2)
        serial_layout.addWidget(QtWidgets.QLabel("波特率:"), 0, 3)
        serial_layout.addWidget(self.baud_combo, 0, 4)
        serial_layout.addWidget(self.open_btn, 0, 5)
        serial_layout.addWidget(self.close_btn, 0, 6)
        
        # --- [ 3. Profile 布局 (使用 QGridLayout) ] ---
        # 我们把 Profile 相关的控件放在第二个、独立的网格布局中
        profile_layout = QtWidgets.QGridLayout()

        self.profile_select_btn = QtWidgets.QPushButton("---请选择Profile---")
        self.profile_info_label = QtWidgets.QLabel("分辨率: N/A")
        self.screen_size_label = QtWidgets.QLabel("尺寸: N/A")

        # 第 0 行 (按钮)
        profile_layout.addWidget(QtWidgets.QLabel("IC Profile:"), 0, 0)
        profile_layout.addWidget(self.profile_select_btn, 0, 1) 
        
        # 第 1 行 (信息)
        # 注意：我们把 "尺寸" 放在 (1, 1)
        profile_layout.addWidget(self.screen_size_label, 1, 1)
        # 注意：我们把 "分辨率" 放在 (1, 2)
        profile_layout.addWidget(self.profile_info_label, 1, 2)

        # --- [ 关键！] ---
        # 添加一个"弹簧"到第 3 列，把 0, 1, 2 列挤在一起
        profile_layout.setColumnStretch(3, 1)
        
        # --- [ 4. 将两个布局添加到顶层 VBox ] ---
        top_level_layout.addLayout(serial_layout)
        top_level_layout.addLayout(profile_layout)
        
        # 2. 核心操作区域
        core_layout = QtWidgets.QHBoxLayout()
        control_group = QtWidgets.QGroupBox("设备控制")
        control_layout = QtWidgets.QVBoxLayout()
        self.reset_btn = QtWidgets.QPushButton("硬件复位 (Reset)")
        # --- [删除] generate_driver_btn 相关的UI代码 ---
        # self.generate_driver_btn = QtWidgets.QPushButton("生成驱动参考...")
        # self.generate_driver_btn.setStyleSheet("background-color: #e0f0ff;")
        # --- 删除结束 ---
        self.init_combo = QtWidgets.QComboBox()
        self.run_init_btn = QtWidgets.QPushButton("执行")
        self.edit_init_btn = QtWidgets.QPushButton("编辑") 
        self.vcom_input = QtWidgets.QComboBox() 
        self.vcom_set_btn = QtWidgets.QPushButton("设置")
        self.osc_freq_combo = QtWidgets.QComboBox()
        self.osc_freq_set_btn = QtWidgets.QPushButton("设置")
        self.lut_combo = QtWidgets.QComboBox()
        self.update_lut_btn = QtWidgets.QPushButton("更新")
        self.delete_lut_btn = QtWidgets.QPushButton("删除")
        self.edit_lut_btn = QtWidgets.QPushButton("参数化波形编辑器...")
        self.flows_layout = QtWidgets.QVBoxLayout()
        self.clear_white_btn = QtWidgets.QPushButton("刷白")
        self.clear_white_btn.setToolTip("建议：使用清屏操作前，请先在上方加载全刷GC波形") # 新增
        self.clear_black_btn = QtWidgets.QPushButton("刷黑")
        self.clear_black_btn.setToolTip("建议：使用清屏操作前，请先在上方加载全刷GC波形") # 新增
        self.clear_grid_btn = QtWidgets.QPushButton("刷新网格")
        self.clear_grid_btn.setToolTip("建议：使用清屏操作前，请先在上方加载全刷GC波形") # 新增
        self.sleep_btn = QtWidgets.QPushButton("进入休眠 (Sleep)")
        init_layout = QtWidgets.QHBoxLayout()
        init_layout.addWidget(QtWidgets.QLabel("初始化序列:"))
        init_layout.addWidget(self.init_combo, 1)
        init_layout.addWidget(self.run_init_btn)
        init_layout.addWidget(self.edit_init_btn)
        params_group = QtWidgets.QGroupBox("参数调节")
        params_layout = QtWidgets.QVBoxLayout(params_group)
        vcom_layout = QtWidgets.QHBoxLayout()
        vcom_layout.addWidget(QtWidgets.QLabel("VCOM Voltage:"))
        vcom_layout.addWidget(self.vcom_input, 1)
        vcom_layout.addWidget(self.vcom_set_btn)
        osc_freq_layout = QtWidgets.QHBoxLayout()
        osc_freq_layout.addWidget(QtWidgets.QLabel("OSC Frequency:"))
        osc_freq_layout.addWidget(self.osc_freq_combo, 1)
        osc_freq_layout.addWidget(self.osc_freq_set_btn)
        params_layout.addLayout(vcom_layout)
        params_layout.addLayout(osc_freq_layout)
        lut_management_layout = QtWidgets.QHBoxLayout()
        lut_management_layout.addWidget(self.lut_combo, 1)
        lut_management_layout.addWidget(self.update_lut_btn)
        lut_management_layout.addWidget(self.delete_lut_btn)
        clear_screen_layout = QtWidgets.QHBoxLayout()
        clear_screen_layout.addWidget(self.clear_white_btn)
        clear_screen_layout.addWidget(self.clear_black_btn)
        clear_screen_layout.addWidget(self.clear_grid_btn)
        control_layout.addWidget(self.reset_btn)
        # --- [删除] 将按钮添加到布局的代码 ---
        # control_layout.addWidget(self.generate_driver_btn)
        # --- 删除结束 ---
        control_layout.addLayout(init_layout)
        control_layout.addWidget(params_group)
        separator1 = QtWidgets.QFrame(); separator1.setFrameShape(QtWidgets.QFrame.HLine); separator1.setFrameShadow(QtWidgets.QFrame.Sunken)
        control_layout.addWidget(separator1)

        # --- [ 新增/移动 代码块 开始 ] ---
        # 将刷新模式添加到 "设备控制"区域, 波形上方
        self.refresh_mode_group = QtWidgets.QGroupBox("刷新模式")
        refresh_mode_layout = QtWidgets.QHBoxLayout(self.refresh_mode_group)
        self.rb_refresh_gc = QtWidgets.QRadioButton("全局刷新 (GC)")
        self.rb_refresh_4gray = QtWidgets.QRadioButton("4灰阶刷新")
        self.rb_refresh_partial = QtWidgets.QRadioButton("局部刷新 (Partial)")
        refresh_mode_layout.addWidget(self.rb_refresh_gc)
        refresh_mode_layout.addWidget(self.rb_refresh_4gray)
        refresh_mode_layout.addWidget(self.rb_refresh_partial)
        refresh_mode_layout.addStretch()
        # 将控件组添加到 control_layout
        control_layout.addWidget(self.refresh_mode_group) 
        # --- [ 新增/移动 代码块 结束 ] ---

        control_layout.addWidget(QtWidgets.QLabel("预设波形:"))
        control_layout.addLayout(lut_management_layout)
        control_layout.addWidget(self.edit_lut_btn)
        separator2 = QtWidgets.QFrame(); separator2.setFrameShape(QtWidgets.QFrame.HLine); separator2.setFrameShadow(QtWidgets.QFrame.Sunken)
        control_layout.addWidget(separator2)
        control_layout.addLayout(self.flows_layout)
        control_layout.addStretch()
        separator3 = QtWidgets.QFrame(); separator3.setFrameShape(QtWidgets.QFrame.HLine); separator3.setFrameShadow(QtWidgets.QFrame.Sunken)
        control_layout.addWidget(separator3)
        control_layout.addWidget(QtWidgets.QLabel("清屏操作:"))
        control_layout.addLayout(clear_screen_layout)
        control_layout.addWidget(self.sleep_btn)
        control_group.setLayout(control_layout)
        
        image_workspace_group = QtWidgets.QGroupBox("图像工作区")
        image_workspace_group.setFixedWidth(880)
        image_workspace_layout = QtWidgets.QVBoxLayout(image_workspace_group)

        # --- [ 删除 代码块 开始 ] ---
        # (原先添加在这里的 refresh_mode_group 代码已被删除)
        # --- [ 删除 代码块 结束 ] ---
        
        v_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        top_widget = QtWidgets.QWidget()
        top_layout = QtWidgets.QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.image_list_widget = QtWidgets.QListWidget()
        self.image_list_widget.setViewMode(QtWidgets.QListView.IconMode)
        self.image_list_widget.setFlow(QtWidgets.QListView.LeftToRight)
        self.image_list_widget.setWrapping(True)
        self.image_list_widget.setResizeMode(QtWidgets.QListView.Adjust)
        self.image_list_widget.setIconSize(QtCore.QSize(100, 100))
        self.image_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        list_button_layout = QtWidgets.QHBoxLayout()
        self.add_images_btn = QtWidgets.QPushButton("添加图片...")
        self.remove_selected_list_btn = QtWidgets.QPushButton("移除选中")
        self.clear_list_btn = QtWidgets.QPushButton("全部清空")
        self.move_left_btn = QtWidgets.QPushButton("← 左移")
        self.move_right_btn = QtWidgets.QPushButton("右移 →")
        list_button_layout.addWidget(self.add_images_btn)
        list_button_layout.addWidget(self.remove_selected_list_btn)
        list_button_layout.addWidget(self.clear_list_btn)
        list_button_layout.addStretch()
        list_button_layout.addWidget(self.move_left_btn)
        list_button_layout.addWidget(self.move_right_btn)
        top_layout.addWidget(self.image_list_widget)
        top_layout.addLayout(list_button_layout)
        
        bottom_widget = QtWidgets.QWidget()
        bottom_layout = QtWidgets.QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        preview_and_settings_container = QtWidgets.QGroupBox("预览与参数")
        preview_and_settings_layout = QtWidgets.QHBoxLayout(preview_and_settings_container)
        self.image_preview_label = QtWidgets.QLabel("点击上方列表中的图片进行预览")
        self.image_preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self.image_preview_label.setMinimumWidth(300)
        self.image_preview_label.setStyleSheet("border: 1px solid gray;")
        settings_group_widget = QtWidgets.QWidget()
        settings_layout = QtWidgets.QGridLayout(settings_group_widget)
        self.display_mode_combo = QtWidgets.QComboBox()
        self.display_mode_combo.addItems(["黑白 (1-bit)", "四灰阶 (2-bit)"])
        self.rotation_combo = QtWidgets.QComboBox()
        self.rotation_combo.addItems(["不旋转", "向右旋转90°", "旋转180°", "向左旋转90°"])
        self.mirror_horizontal_cb = QtWidgets.QCheckBox("水平镜像")
        self.mirror_vertical_cb = QtWidgets.QCheckBox("垂直翻转")
        self.invert_color_checkbox = QtWidgets.QCheckBox("颜色反转")
        self.invert_color_checkbox.setChecked(False)
        self.dither_bw_label = QtWidgets.QLabel("黑白算法:")
        self.dither_bw_combo = QtWidgets.QComboBox()
        self.dither_bw_combo.addItems(["无", "阈值法", "Floyd-Steinberg"])
        self.dither_4gray_label = QtWidgets.QLabel("四灰阶算法:")
        self.dither_4gray_combo = QtWidgets.QComboBox()
        self.dither_4gray_combo.addItems(["无", "Floyd-Steinberg", "Burkes", "Stucki", "Atkinson"])
        self.threshold_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.threshold_slider.setRange(0, 255); self.threshold_slider.setValue(128)
        self.threshold_label = QtWidgets.QLabel("阈值: 128")
        settings_layout.addWidget(QtWidgets.QLabel("目标模式:"), 0, 0)
        settings_layout.addWidget(self.display_mode_combo, 0, 1, 1, 3)
        settings_layout.addWidget(QtWidgets.QLabel("变换:"), 1, 0)
        settings_layout.addWidget(self.rotation_combo, 1, 1)
        settings_layout.addWidget(self.mirror_horizontal_cb, 1, 2)
        settings_layout.addWidget(self.mirror_vertical_cb, 1, 3)
        settings_layout.addWidget(self.invert_color_checkbox, 2, 1, 1, 3)
        separator = QtWidgets.QFrame(); separator.setFrameShape(QtWidgets.QFrame.HLine); separator.setFrameShadow(QtWidgets.QFrame.Sunken)
        settings_layout.addWidget(separator, 3, 0, 1, 4)
        settings_layout.addWidget(self.dither_bw_label, 4, 0)
        settings_layout.addWidget(self.dither_bw_combo, 4, 1, 1, 3)
        settings_layout.addWidget(self.dither_4gray_label, 5, 0)
        settings_layout.addWidget(self.dither_4gray_combo, 5, 1, 1, 3)
        settings_layout.addWidget(self.threshold_slider, 6, 0, 1, 3)
        settings_layout.addWidget(self.threshold_label, 6, 3)
        settings_layout.setRowStretch(7, 1)
        preview_and_settings_layout.addWidget(self.image_preview_label, 1)
        preview_and_settings_layout.addWidget(settings_group_widget)
        
        execution_group = QtWidgets.QGroupBox("执行")
        execution_layout = QtWidgets.QGridLayout(execution_group)
        
        self.loop_queue_checkbox = QtWidgets.QCheckBox("循环发送")
        self.interval_spinbox = QtWidgets.QSpinBox()
        self.interval_spinbox.setSuffix(" 毫秒")
        self.interval_spinbox.setRange(1, 600000)
        self.interval_spinbox.setValue(1000)
        
        self.send_queue_btn = QtWidgets.QPushButton("开始发送")
        self.send_queue_btn.setObjectName("send_queue_btn")
        self.pause_resume_btn = QtWidgets.QPushButton("暂停")
        self.pause_resume_btn.setObjectName("pause_resume_btn")
        self.pause_resume_btn.setEnabled(False) 
        self.export_array_btn = QtWidgets.QPushButton("导出预览图数组...")
        self.upload_progress_bar = QtWidgets.QProgressBar()
        
        # --- [ 修改 ] ---
        # 确认行索引是 0 和 1
        execution_layout.addWidget(QtWidgets.QLabel("刷新间隔:"), 0, 0)
        execution_layout.addWidget(self.interval_spinbox, 0, 1)
        execution_layout.addWidget(self.loop_queue_checkbox, 0, 2)
        execution_layout.addWidget(self.send_queue_btn, 1, 0, 1, 1)
        execution_layout.addWidget(self.pause_resume_btn, 1, 1, 1, 1)
        execution_layout.addWidget(self.export_array_btn, 1, 2, 1, 1)
        # --- [ 修改结束 ] ---

        bottom_layout.addWidget(preview_and_settings_container)
        bottom_layout.addWidget(execution_group)
        bottom_layout.addWidget(self.upload_progress_bar)
        v_splitter.addWidget(top_widget)
        v_splitter.addWidget(bottom_widget)
        v_splitter.setSizes([200, 500])
        image_workspace_layout.addWidget(v_splitter)
        core_layout.addWidget(control_group)
        core_layout.addWidget(image_workspace_group)
        core_layout.addStretch(1)
        log_group = QtWidgets.QGroupBox("日志输出")
        title_bar_layout = QtWidgets.QHBoxLayout()
        title_bar_layout.addStretch() 
        self.clear_log_btn = QtWidgets.QPushButton("清空")
        title_bar_layout.addWidget(self.clear_log_btn)
        main_log_layout = QtWidgets.QVBoxLayout(log_group)
        main_log_layout.addLayout(title_bar_layout) 
        self.text_area = QtWidgets.QTextEdit()
        self.text_area.setReadOnly(True)
        main_log_layout.addWidget(self.text_area)
        
        main_layout = QtWidgets.QVBoxLayout(central_widget)
        main_layout.addWidget(connection_group)
        main_layout.addLayout(core_layout)
        main_layout.addWidget(log_group, 1)