import sys
import os
import json
import re
import serial
import serial.tools.list_ports
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QEventLoop, QTimer
from PyQt5.QtWidgets import QMainWindow, QFileDialog, QMessageBox
import shutil  # <-- 新增导入，用于复制文件夹

from ui_main_window import Ui_MainWindow
import shutil
from serial_worker import SerialWorker
from script_executor import ScriptExecutor
from waveform_editor import WaveformEditorDialog
from image_processor import ImageProcessor
from code_generator import DriverCodeGenerator
from user_guide_dialog import UserGuideDialog
import utils

from workers.display_worker import DisplayWorker  # <-- [ 新增 ] 导入我们刚创建的类
from workers.multi_image_worker import MultiImageDisplayWorker # <-- [ 新增 ] 导入新类
from workers.lut_update_worker import LutUpdateWorker # <-- [ 新增 ] 导入新类
from workers.device_scanner import DeviceScanner # <-- [ 新增 ] 导入新类


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


class FlowWorker(QObject):
    finished = pyqtSignal(bool, str)
    log_message = pyqtSignal(str, bool)
    def __init__(self, serial_worker, profile, steps, parent=None):
        super().__init__(parent)
        self.serial_worker = serial_worker
        self.profile = profile
        self.steps = steps
        self.is_running = True
    def run(self):
        total_steps = len(self.steps)
        for i, step in enumerate(self.steps):
            if not self.is_running: self.finished.emit(False, "流程被用户取消"); return
            step_name = step.get('name', step.get('type'))
            self.log_message.emit(f"[FLOW] 执行步骤 {i+1}/{total_steps}: {step_name}", False)
            step_type = step.get("type")
            success, message = False, f"未知步骤类型: {step_type}"
            try:
                if step_type == "init": success, message = self._execute_init_step(step)
                elif step_type == "script": success, message = self._execute_script_step(step)
                if not success: self.finished.emit(False, f"步骤 '{step_name}' 失败: {message}"); return
            except Exception as e:
                self.finished.emit(False, f"执行步骤 '{step_name}' 时发生意外错误: {e}"); return
        self.finished.emit(True, "流程执行完毕")
    def _execute_script_step(self, step):
        script_key = step.get("key");
        if not script_key: return False, "流程步骤'script'缺少'key'参数"
        scripts = self.profile.get("scripts", {}); relative_script_path = scripts.get(script_key)
        if not relative_script_path: return False, f"未在Profile的scripts中找到名为'{script_key}'的脚本"
        return self._run_script_file(relative_script_path)
    def _execute_init_step(self, step):
        init_name = step.get("name"); init_map = self.profile.get("initializations", {});
        relative_script_path = init_map.get(init_name)
        if not relative_script_path: return False, f"未在Profile中找到名为 '{init_name}' 的初始化脚本"
        return self._run_script_file(relative_script_path)
    def _run_script_file(self, relative_script_path):
        profile_root = self.profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        executor = ScriptExecutor(self.serial_worker); executor.log_message.connect(self.log_message)
        try:
            with open(absolute_script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
            success, msg = executor._parse_and_execute(lines); QThread.msleep(50)
            return success, msg
        except Exception as e: return False, str(e)
    def stop(self): self.is_running = False

def get_base_path():
    """获取基础路径，兼容开发环境和打包后的环境"""
    base_path = "" # 初始化
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 如果是打包后的环境 (PyInstaller)
        base_path = os.path.dirname(sys.executable)
        #print(f"--- DEBUG: Running in bundled mode. sys.executable: {sys.executable}") # 调试信息
    else:
        # 如果是开发环境 (直接运行 .py)
        base_path = os.path.dirname(os.path.abspath(__file__))
        #print(f"--- DEBUG: Running in development mode. __file__: {__file__}") # 调试信息
        
    #print(f"--- DEBUG: get_base_path() determined base_path: {base_path}") # 调试信息
    return base_path

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()

         # --- [ 新增 ] ---
        self.profile_menu = QtWidgets.QMenu(self) # 用于存放 Profile 菜单


        self.profiles, self.current_profile = {}, None
        self.serial_thread, self.serial_worker, self.executor = None, None, None
        self.lut_thread, self.lut_worker = None, None
        self.image_thread, self.image_worker = None, None
        self.scanner_thread, self.scanner = None, None
        self.flow_thread, self.flow_worker = None, None
        self.multi_image_thread = None
        self.multi_image_worker = None
        
        # --- [ 新增代码 ] ---
        # 用于缓存上一帧的图像数据，以实现局刷
        self.last_image_bytes = None
        # --- [ 新增结束 ] ---

        self.image_queue = [] 
        self.current_preview_path = None
        self.processed_preview_image = None
        self.is_task_paused = False
        
        self.setupUi(self)

        self._create_menu_bar()

        self.image_list_widget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.image_list_widget.setDefaultDropAction(QtCore.Qt.MoveAction)
        
        self._populate_vcom_combo()
        self._populate_osc_freq_combo()
        self._connect_signals()
        self._load_profiles()
        self.scan_devices()
        self.update_lut_combo()
        self.update_init_combo()
        self._on_display_mode_changed()

    
    def _create_menu_bar(self):
        """创建并初始化顶部菜单栏"""
        menu_bar = self.menuBar()

        # 添加 "文件" 菜单
        file_menu = menu_bar.addMenu('文件')
        # 添加 "设置路径" 动作
        settings_action = QtWidgets.QAction('设置 Profile 路径...', self)
        settings_action.triggered.connect(self.select_profiles_directory)
        file_menu.addAction(settings_action)

        # --- [新添加] 工具菜单 ---
        tools_menu = menu_bar.addMenu("工具(T)")
        generate_driver_action = QtWidgets.QAction("生成驱动参考...", self)
        generate_driver_action.setStatusTip("根据当前Profile生成C语言驱动参考代码")
        generate_driver_action.triggered.connect(self.handle_generate_driver_code)
        tools_menu.addAction(generate_driver_action)
        # --- 添加结束 ---

        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助(H)")
        show_guide_action = QtWidgets.QAction("查看帮助文档", self)
        show_guide_action.setStatusTip("打开快速入门指南")
        show_guide_action.triggered.connect(self.handle_show_help)
        help_menu.addAction(show_guide_action)

    def select_profiles_directory(self):
        """
        打开一个对话框，让用户选择 'profiles' 文件夹。
        """
        # 1. 获取当前路径，作为对话框的起始点
        current_path = utils.get_user_data_path("profiles")
        
        # 2. 打开文件夹选择对话框
        new_path = QFileDialog.getExistingDirectory(
            self,
            "请选择 'profiles' 文件夹",
            current_path  # 对话框的默认起始位置
        )
        
        # 3. 如果用户选择了新路径
        if new_path and new_path != current_path:
            
            # 4. (可选但推荐) 检查新路径是否包含有效的 profile 文件
            #    这里我们暂时简化，直接保存。
            
            # 5. 保存新路径到 settings.ini
            success = utils.save_custom_profiles_path(new_path)
            
            if success:
                # 6. 通知用户并重新加载
                QMessageBox.information(self,
                    "路径已更新",
                    f"Profile 路径已更新为:\n{new_path}\n\n"
                    "程序将立即重新加载 Profile。")
                
                # 立即使用新路径重新加载
                self._load_profiles()
            else:
                QMessageBox.warning(self, "错误", "无法保存设置文件 'settings.ini'。")

    def _populate_vcom_combo(self):
        self.vcom_input.clear()
        for dec_val in range(0, 80):
            voltage = -0.10 - dec_val * 0.05
            self.vcom_input.addItem(f"{voltage:.2f}V", userData=dec_val)

    def _connect_signals(self):
        # 连接与配置
        self.refresh_btn.clicked.connect(self.scan_devices)
        self.open_btn.clicked.connect(self.open_serial)
        self.close_btn.clicked.connect(self.close_serial)
        
        # (新增 profile_select_btn 的信号连接)
        self.profile_select_btn.clicked.connect(self.show_profile_menu)
        self.profile_menu.triggered.connect(self._on_profile_action_selected)
        # 设备控制
        self.reset_btn.clicked.connect(lambda: self._execute_script_by_key("reset"))
        self.edit_init_btn.clicked.connect(self.handle_edit_init_script)
        self.update_lut_btn.clicked.connect(self.handle_update_lut_from_combo)
        self.delete_lut_btn.clicked.connect(self.handle_delete_lut)
        self.edit_lut_btn.clicked.connect(self.handle_open_waveform_editor)
        self.sleep_btn.clicked.connect(lambda: self._execute_script_by_key("sleep"))
        self.clear_white_btn.clicked.connect(lambda: self._start_fill_task('white'))
        self.clear_black_btn.clicked.connect(lambda: self._start_fill_task('black'))
        self.clear_grid_btn.clicked.connect(lambda: self._start_fill_task('grid'))
        self.init_combo.currentIndexChanged.connect(self.update_vcom_control_from_script)
        self.vcom_set_btn.clicked.connect(self.handle_set_vcom)
        self.osc_freq_set_btn.clicked.connect(self.handle_set_osc_freq)
        self.run_init_btn.clicked.connect(self.handle_run_init_from_combo)
        # --- [删除] 旧按钮的信号连接 ---
        # self.generate_driver_btn.clicked.connect(self.handle_generate_driver_code)
        # --- 删除结束 ---
        
        # 图像工作区信号连接
        self.add_images_btn.clicked.connect(self.handle_add_images_to_queue)
        self.remove_selected_list_btn.clicked.connect(self.handle_remove_selected_images)
        self.clear_list_btn.clicked.connect(self.handle_clear_image_queue)
        self.image_list_widget.currentItemChanged.connect(self._on_image_item_selected)
        self.image_list_widget.model().rowsMoved.connect(self.on_image_queue_reordered)
        self.move_left_btn.clicked.connect(self.handle_move_item_left)
        self.move_right_btn.clicked.connect(self.handle_move_item_right)
        self.pause_resume_btn.clicked.connect(self.handle_pause_resume)
        self.send_queue_btn.clicked.connect(self.handle_start_sending_queue)
        self.export_array_btn.clicked.connect(self.handle_export_array)
        
        # 图像参数变化的信号都连接到预览更新
        self.display_mode_combo.currentIndexChanged.connect(self._on_display_mode_changed)
        self.rotation_combo.currentIndexChanged.connect(self.process_and_preview_image)
        self.mirror_horizontal_cb.stateChanged.connect(self.process_and_preview_image)
        self.mirror_vertical_cb.stateChanged.connect(self.process_and_preview_image)
        self.invert_color_checkbox.stateChanged.connect(self.process_and_preview_image)
        self.dither_bw_combo.currentIndexChanged.connect(self._on_dither_method_changed)
        self.dither_4gray_combo.currentIndexChanged.connect(self.process_and_preview_image)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)

        # 日志
        self.clear_log_btn.clicked.connect(self.text_area.clear)

        # --- [ 新增代码块 开始 ] ---
        # 刷新模式 和 图像处理模式 联动
        self.rb_refresh_gc.toggled.connect(self._on_refresh_mode_changed)
        self.rb_refresh_4gray.toggled.connect(self._on_refresh_mode_changed)
        self.rb_refresh_partial.toggled.connect(self._on_refresh_mode_changed)
        # --- [ 新增代码块 结束 ] ---

    def set_controls_enabled(self, enabled):
        # 设备控制
        self.reset_btn.setEnabled(enabled)
        self.run_init_btn.setEnabled(enabled)
        self.edit_init_btn.setEnabled(enabled)
        self.update_lut_btn.setEnabled(enabled)
        self.delete_lut_btn.setEnabled(enabled)
        self.edit_lut_btn.setEnabled(enabled)
        self.sleep_btn.setEnabled(enabled)
        self.clear_white_btn.setEnabled(enabled)
        self.clear_black_btn.setEnabled(enabled)
        self.clear_grid_btn.setEnabled(enabled)
        self.vcom_input.setEnabled(enabled)
        self.vcom_set_btn.setEnabled(enabled)
        
        # 图像工作区
        self.add_images_btn.setEnabled(enabled)
        self.remove_selected_list_btn.setEnabled(enabled)
        self.clear_list_btn.setEnabled(enabled)
        self.pause_resume_btn.setEnabled(False)
        self.send_queue_btn.setEnabled(enabled)
        self.export_array_btn.setEnabled(enabled)
        self.loop_queue_checkbox.setEnabled(enabled)
        self.interval_spinbox.setEnabled(enabled)
        # 流程按钮
        for i in range(self.flows_layout.count()):
            widget = self.flows_layout.itemAt(i).widget()
            if widget: widget.setEnabled(enabled)
            
    def handle_generate_driver_code(self):
        if not self.current_profile:
            QtWidgets.QMessageBox.warning(self, "操作无效", "请先从顶部选择一个IC Profile。")
            return
        dialog = CodeGenOptionsDialog(self)
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            parts = dialog.get_selected_parts()
            if not parts:
                self.log_to_textarea("[INFO] 未选择任何代码部分，操作取消。")
                return
            try:
                self.log_to_textarea(f"[ACTION] 正在为 '{self.current_profile['ic_name']}' 生成选定的驱动代码...")
                generator = DriverCodeGenerator(self.current_profile)
                generated_code = generator.generate_code(parts)
                self._show_generated_code_dialog(generated_code)
            except Exception as e:
                error_msg = f"生成驱动代码时出错: {e}"
                self.log_to_textarea(f"[ERROR] {error_msg}", True)
                QtWidgets.QMessageBox.critical(self, "生成失败", error_msg)

    def _show_generated_code_dialog(self, code):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(f"{self.current_profile['ic_name']} - 驱动参考代码")
        dialog.setMinimumSize(700, 800)
        layout = QtWidgets.QVBoxLayout(dialog)
        text_edit = QtWidgets.QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QtGui.QFont("Courier New", 10))
        text_edit.setText(code)
        copy_btn = QtWidgets.QPushButton("复制全部代码到剪贴板")
        def copy_to_clipboard():
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(code)
            self.log_to_textarea("[SUCCESS] 代码已复制到剪贴板。")
        copy_btn.clicked.connect(copy_to_clipboard)
        layout.addWidget(text_edit)
        layout.addWidget(copy_btn)
        dialog.exec_()
        
    def _on_image_item_selected(self, current_item, previous_item):
        if current_item:
            path = current_item.data(QtCore.Qt.UserRole)
            if path != self.current_preview_path:
                self.current_preview_path = path
                self.log_to_textarea(f"[UI] 切换预览至: {os.path.basename(path)}")
                self.process_and_preview_image()
        else:
            self.current_preview_path = None
            self.processed_preview_image = None
            self.image_preview_label.setText("点击上方列表中的图片进行预览")

    def handle_move_item_left(self):
        selected_item = self.image_list_widget.currentItem()
        if not selected_item: return
        current_row = self.image_list_widget.row(selected_item)
        if current_row > 0:
            self.image_queue[current_row], self.image_queue[current_row - 1] = self.image_queue[current_row - 1], self.image_queue[current_row]
            self._update_image_list_widget()
            self.image_list_widget.setCurrentRow(current_row - 1)           

    def handle_move_item_right(self):
        selected_item = self.image_list_widget.currentItem()
        if not selected_item: return
        current_row = self.image_list_widget.row(selected_item)
        if current_row < self.image_list_widget.count() - 1:
            self.image_queue[current_row], self.image_queue[current_row + 1] = self.image_queue[current_row + 1], self.image_queue[current_row]
            self._update_image_list_widget()
            self.image_list_widget.setCurrentRow(current_row + 1)
            
    def process_and_preview_image(self):
        if not self.current_preview_path or not os.path.exists(self.current_preview_path): return
        if not self.current_profile:
            pixmap = QtGui.QPixmap(self.current_preview_path)
            scaled_pixmap = pixmap.scaled(self.image_preview_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.image_preview_label.setPixmap(scaled_pixmap)
            return
        res = self.current_profile.get("resolution", {}); width, height = res.get("width"), res.get("height")
        if not width or not height: return
        try:
            self.processed_preview_image, _ = self._process_single_image(self.current_preview_path)
            if self.processed_preview_image:
                qpixmap = ImageProcessor.pil_to_qpixmap(self.processed_preview_image)
                scaled_pixmap = qpixmap.scaled(self.image_preview_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                self.image_preview_label.setPixmap(scaled_pixmap)
        except Exception as e:
            self.log_to_textarea(f"[ERROR] 图像预览处理失败: {e}", True)
            self.processed_preview_image = None

    def _process_single_image(self, image_path):
        if not self.current_profile: return None, None
        res = self.current_profile.get("resolution", {}); width, height = res.get("width"), res.get("height")
        if not width or not height: return None, None
        try:
            rotation_map = {0: 0, 1: 90, 2: 180, 3: 270}
            rotation = rotation_map.get(self.rotation_combo.currentIndex(), 0)
            process_args = { "rotation": rotation, "invert_color": self.invert_color_checkbox.isChecked(), "mirror_horizontal": self.mirror_horizontal_cb.isChecked(), "mirror_vertical": self.mirror_vertical_cb.isChecked() }
            is_bw_mode = self.display_mode_combo.currentIndex() == 0
            image_mode = ""
            if is_bw_mode:
                bw_method = self.dither_bw_combo.currentText()
                if bw_method == "Floyd-Steinberg": image_mode = "floyd-steinberg"
                elif bw_method == "阈值法":
                    image_mode = "threshold"; process_args["threshold_value"] = self.threshold_slider.value()
                else:
                    image_mode = "threshold"; process_args["threshold_value"] = 128
            else:
                image_mode = "4gray"
                dither_method = self.dither_4gray_combo.currentText()
                if dither_method != "无":
                    process_args["dither_method"] = dither_method
            if not image_mode: return None, None
            processed_pil_img = ImageProcessor.process_image(image_path, (width, height), image_mode, **process_args)
            bytes_data = None
            if is_bw_mode:
                bytes_data = processed_pil_img.tobytes()
            else:
                bytes_data = ImageProcessor.pack_4gray_data_for_ssd(processed_pil_img)
            return processed_pil_img, bytes_data
        except Exception as e:
            self.log_to_textarea(f"[ERROR] 后台处理图片 {os.path.basename(image_path)} 失败: {e}", True)
            return None, None
    
    def handle_add_images_to_queue(self):
        if self.is_any_task_running(): return
        image_paths, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "选择要添加到队列的图片", "", "Image Files (*.png *.jpg *.jpeg *.bmp)"
        )
        if not image_paths: return
        is_first_add = not self.image_queue
        for path in image_paths:
            if path not in self.image_queue:
                self.image_queue.append(path)
        self.log_to_textarea(f"[INFO] 添加了 {len(image_paths)} 张图片到队列。")
        self._update_image_list_widget()
        if is_first_add and self.image_queue:
            self.image_list_widget.setCurrentRow(0)

    def _update_image_list_widget(self):
        current_path = self.current_preview_path
        self.image_list_widget.blockSignals(True)
        self.image_list_widget.clear()
        new_index_to_select = -1
        for i, path in enumerate(self.image_queue):
            item = QtWidgets.QListWidgetItem()
            item.setIcon(QtGui.QIcon(path))
            item.setToolTip(os.path.basename(path))
            item.setData(QtCore.Qt.UserRole, path)
            self.image_list_widget.addItem(item)
            if path == current_path:
                new_index_to_select = i
        self.image_list_widget.blockSignals(False)
        if new_index_to_select != -1:
            self.image_list_widget.setCurrentRow(new_index_to_select)
        elif not self.image_queue:
            self._on_image_item_selected(None, None)

    def handle_remove_selected_images(self):
        selected_items = self.image_list_widget.selectedItems()
        if not selected_items: return
        for item in selected_items:
            path_to_remove = item.data(QtCore.Qt.UserRole)
            if path_to_remove in self.image_queue:
                self.image_queue.remove(path_to_remove)
        self.log_to_textarea(f"[INFO] 从队列中移除了 {len(selected_items)} 张图片。")
        self._update_image_list_widget()

    def handle_clear_image_queue(self):
        if not self.image_queue: return
        reply = QtWidgets.QMessageBox.question(self, '确认', "确定要清空整个发送队列吗？", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            self.image_queue.clear()
            self._update_image_list_widget()
            self.log_to_textarea("[INFO] 发送队列已清空。")
            
    def on_image_queue_reordered(self):
        new_queue = []
        for i in range(self.image_list_widget.count()):
            item = self.image_list_widget.item(i)
            path = item.data(QtCore.Qt.UserRole)
            new_queue.append(path)
        self.image_queue = new_queue
        self.log_to_textarea("[UI] 图片队列顺序已更新。")
        
    def handle_start_sending_queue(self):
        if self.is_any_task_running(): return
        if not self.serial_worker: QtWidgets.QMessageBox.warning(self, "错误", "请先连接设备。"); return
        if not self.current_profile: QtWidgets.QMessageBox.warning(self, "错误", "请先选择一个Profile。"); return
        if not self.image_queue: QtWidgets.QMessageBox.information(self, "提示", "发送队列为空，请先添加图片。"); return
        
        is_looping = self.loop_queue_checkbox.isChecked()
        interval_ms = self.interval_spinbox.value()

        # --- [ 核心修改：根据单选框决定脚本 ] ---
        
        script_key = None
        is_partial_mode = False
        
        if self.rb_refresh_gc.isChecked():
            script_key = "display_full_gc"
        elif self.rb_refresh_4gray.isChecked():
            script_key = "display_4gray"
        elif self.rb_refresh_partial.isChecked():
            script_key = "display_partial"
            is_partial_mode = True # 激活局刷逻辑

        if not script_key:
            QtWidgets.QMessageBox.warning(self, "错误", f"未选择有效的刷新模式。")
            return

        scripts = self.current_profile.get("scripts", {})
        relative_script_path = scripts.get(script_key)
        
        if not relative_script_path:
            QtWidgets.QMessageBox.warning(self, "脚本缺失", f"当前Profile中未定义 '{script_key}' 脚本。")
            return
            
        profile_root = self.current_profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        if not os.path.exists(absolute_script_path):
            QtWidgets.QMessageBox.warning(self, "脚本未找到", f"脚本文件不存在: {absolute_script_path}")
            return

        def data_processor_for_worker(image_path):
            # 1. 正常处理新图片
            #    (图像处理模式由 display_mode_combo 决定)
            _, new_bytes_data = self._process_single_image(image_path) #
            if new_bytes_data is None:
                return None # 处理失败
            
            # --- [ 核心修复：开始 ] ---
            # 检查新数据是 B/W (bytes) 还是 4Gray (tuple)
            is_new_data_bw = isinstance(new_bytes_data, bytes)
            
            # 2. 根据模式决定返回内容
            if is_partial_mode:
                # --- 局刷逻辑 (0x10h + 0x13h) ---
                old_bytes_data = self.last_image_bytes
                if old_bytes_data is None:
                    # 第一次局刷, 或上一次是4Gray, 用 0xFF 填充
                    # 我们假设局刷时，新数据(new_bytes_data)一定是B/W (bytes)
                    data_len = len(new_bytes_data) if is_new_data_bw else (self.current_profile.get("resolution", {}).get("width", 0) * self.current_profile.get("resolution", {}).get("height", 0) // 8)
                    if data_len == 0:
                        self.log_to_textarea("[ERROR] 无法获取局刷数据长度", True)
                        return None
                    old_bytes_data = bytearray([0xFF] * data_len)
                    self.log_to_textarea("[INFO] 局刷：旧数据(0x10h)自动填充 0xFF。", False)
                
                # 更新缓存: 只有 B/W (bytes) 数据可以被缓存用于局刷
                if is_new_data_bw:
                    self.last_image_bytes = new_bytes_data
                else:
                    self.last_image_bytes = None # 4-gray (tuple) 数据不能被缓存
                
                # 返回 (旧数据, 新数据) 元组
                return (old_bytes_data, new_bytes_data)
            else:
                # --- 全刷或4灰阶逻辑 ---
                
                # 更新缓存: 只有 B/W (bytes) 数据可以被缓存用于局刷
                if is_new_data_bw:
                    self.last_image_bytes = new_bytes_data
                else:
                    self.last_image_bytes = None # 4-gray (tuple) 数据不能被缓存
                
                # 返回新数据 (B/W的bytes 或 4Gray的tuple)
                return new_bytes_data 
            # --- [ 核心修复：结束 ] ---

        task_name = f"发送队列中的 {len(self.image_queue)} 张图片"
        self._start_multi_display_task(absolute_script_path, lambda: self.image_queue, data_processor_for_worker, task_name, is_looping, interval_ms)


    def handle_export_array(self):
        if self.is_any_task_running(): return
        if not self.processed_preview_image: QtWidgets.QMessageBox.warning(self, "操作无效", "没有可导出的预览图。"); return
        _, image_data = self._process_single_image(self.current_preview_path)
        if image_data is None: return
        dialog = QtWidgets.QDialog(self); dialog.setWindowTitle("导出的C语言数组"); dialog.setMinimumSize(500, 400)
        layout = QtWidgets.QVBoxLayout(dialog); text_edit = QtWidgets.QTextEdit(); text_edit.setReadOnly(True)
        text_edit.setFont(QtGui.QFont("Courier New", 10)); full_text = ""
        if isinstance(image_data, (list, tuple)):
            full_text += ImageProcessor.format_bytes_as_c_array(image_data[0], "gImage_Buffer_1") + "\n\n"
            full_text += ImageProcessor.format_bytes_as_c_array(image_data[1], "gImage_Buffer_2")
        else: full_text += ImageProcessor.format_bytes_as_c_array(image_data)
        text_edit.setText(full_text); layout.addWidget(text_edit); dialog.exec_()
        
    def _start_multi_display_task(self, script_path, image_paths_func, process_func, task_name, is_looping, interval_ms):
        self.multi_image_thread = QThread(self)
        self.multi_image_worker = MultiImageDisplayWorker(
            self.serial_worker, script_path, image_paths_func, process_func, task_name, 
            is_looping, interval_ms
        )
        self.multi_image_worker.moveToThread(self.multi_image_thread)
        self.multi_image_worker.finished.connect(self.on_display_task_finished)
        self.multi_image_worker.log_message.connect(self.log_to_textarea)
        def update_multi_progress(current_idx, total, name, percent):
            self.upload_progress_bar.setFormat(f"发送中: {name} ({current_idx}/{total}) - {percent}%")
            total_progress = ((current_idx - 1) * 100 + percent) / total
            self.upload_progress_bar.setValue(int(total_progress))
        self.multi_image_worker.progress.connect(update_multi_progress)
        self.multi_image_worker.finished.connect(self.multi_image_thread.quit)
        self.multi_image_thread.finished.connect(self.multi_image_worker.deleteLater)
        self.multi_image_thread.finished.connect(lambda: setattr(self, 'multi_image_thread', None))
        self.multi_image_thread.started.connect(self.multi_image_worker.run)
        self.log_to_textarea(f"[ACTION] 请求: {task_name} (循环: {is_looping}, 间隔: {interval_ms}ms)...")
        self.upload_progress_bar.setFormat("准备中...")
        self.upload_progress_bar.setValue(0)
        self.set_controls_enabled(False)
        self.is_task_paused = False
        self.pause_resume_btn.setText("暂停")
        self.pause_resume_btn.setEnabled(True)
        self.multi_image_thread.start()

    def _on_display_mode_changed(self):
        is_bw_mode = self.display_mode_combo.currentIndex() == 0
        self.dither_bw_label.setVisible(is_bw_mode)
        self.dither_bw_combo.setVisible(is_bw_mode)
        self.threshold_slider.setVisible(is_bw_mode)
        self.threshold_label.setVisible(is_bw_mode)
        self.dither_4gray_label.setVisible(not is_bw_mode)
        self.dither_4gray_combo.setVisible(not is_bw_mode)
        self._on_dither_method_changed()

    # --- [ 新增函数 开始 ] ---
    def _on_refresh_mode_changed(self):
        """
        当刷新模式(GC/4Gray/Partial)单选框变化时，
        锁定或解锁 图像处理(B/W, 4Gray)下拉框的选项
        """
        # QComboBox 的 Item 索引:
        # 0: 黑白 (1-bit)
        # 1: 四灰阶 (2-bit)
        
        if self.rb_refresh_4gray.isChecked():
            # 模式: 4灰阶刷新
            # - 允许选择 4灰阶
            self.display_mode_combo.model().item(1).setEnabled(True)
            # - 强制选择 4灰阶
            self.display_mode_combo.setCurrentIndex(1)
            # - (可选) 禁用 B/W
            self.display_mode_combo.model().item(0).setEnabled(False)
            
        elif self.rb_refresh_gc.isChecked() or self.rb_refresh_partial.isChecked():
            # 模式: 全局刷新 或 局部刷新
            # - 允许选择 B/W
            self.display_mode_combo.model().item(0).setEnabled(True)
            # - 禁用 4灰阶 (GC 和 Partial 都不支持 4灰阶处理模式)
            self.display_mode_combo.model().item(1).setEnabled(False)
            # - 强制选择 B/W
            self.display_mode_combo.setCurrentIndex(0)
            
        # 确保 display_mode_combo 本身是可用的
        self.display_mode_combo.setEnabled(True)


        # --- [ 新增代码 ] ---
        # 触发 Lut 下拉框的刷新，以根据新模式进行过滤
        self.update_lut_combo() 
        # --- [ 新增结束 ] ---
    # --- [ 新增函数 结束 ] ---

    def _on_dither_method_changed(self):
        is_threshold_method = self.dither_bw_combo.currentText() == "阈值法"
        self.threshold_slider.setEnabled(is_threshold_method)
        self.process_and_preview_image()

    def _on_threshold_changed(self, value):
        self.threshold_label.setText(f"阈值: {value}")
        if self.threshold_slider.isEnabled():
            self.process_and_preview_image()
    
    def _get_current_init_script_path(self):
        if not self.current_profile: return None
        selected_init_name = self.init_combo.currentText()
        if not selected_init_name or "无初始化脚本" in selected_init_name: return None
        init_map = self.current_profile.get("initializations", {})
        relative_script_path = init_map.get(selected_init_name)
        if not relative_script_path and selected_init_name == "Default Init":
            relative_script_path = self.current_profile.get("init_script")
        if not relative_script_path: return None
        profile_root = self.current_profile.get('__root_path__')
        return os.path.abspath(os.path.join(profile_root, relative_script_path))
    
    def update_vcom_control_from_script(self):
        script_path = self._get_current_init_script_path()
        found = False
        if script_path and os.path.exists(script_path):
            try:
                with open(script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
                found_vcom_cmd_line = -1
                for i, line in enumerate(lines):
                    if re.search(r'\bCMD\s+0x82\b', line, re.IGNORECASE): found_vcom_cmd_line = i; break
                if found_vcom_cmd_line != -1 and found_vcom_cmd_line + 1 < len(lines):
                    next_line = lines[found_vcom_cmd_line + 1].strip()
                    if next_line.upper().startswith("DATA"):
                        match = re.search(r'0x[0-9a-fA-F]{1,2}', next_line)
                        if match:
                            hex_val = match.group(0)
                            target_dec_val = int(hex_val, 16)
                            index = self.vcom_input.findData(target_dec_val)
                            if index != -1:
                                self.vcom_input.setCurrentIndex(index)
                                found = True
                            else:
                                self.log_to_textarea(f"[WARN] 脚本中的VCOM值 {hex(target_dec_val)} 不在预设列表中。", True)
            except Exception as e:
                self.log_to_textarea(f"[ERROR] 解析VCOM电压时出错: {e}", True)
        is_enabled = found and self.serial_worker is not None
        self.vcom_input.setEnabled(is_enabled)
        self.vcom_set_btn.setEnabled(is_enabled)
        if not found: self.vcom_input.setCurrentIndex(-1)                                

    def handle_set_vcom(self):
        script_path = self._get_current_init_script_path()
        if not script_path or not os.path.exists(script_path): return
        selected_index = self.vcom_input.currentIndex()
        if selected_index == -1: return
        dec_val = self.vcom_input.itemData(selected_index)
        voltage_text = self.vcom_input.itemText(selected_index)
        new_vcom_hex_text = f"0x{dec_val:02X}"
        try:
            with open(script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
            found_vcom_cmd_line = -1
            for i, line in enumerate(lines):
                if re.search(r'\bCMD\s+0x82\b', line, re.IGNORECASE): found_vcom_cmd_line = i; break
            if found_vcom_cmd_line != -1 and found_vcom_cmd_line + 1 < len(lines):
                data_line_index = found_vcom_cmd_line + 1
                original_data_line = lines[data_line_index]
                if original_data_line.strip().upper().startswith("DATA"):
                    lines[data_line_index] = re.sub(r'0x[0-9a-fA-F]{1,2}', new_vcom_hex_text, original_data_line, count=1)
                    with open(script_path, 'w', encoding='utf-8') as f: f.write("".join(lines))
                    self.log_to_textarea(f"[SUCCESS] 脚本VCOM值已更新为 {new_vcom_hex_text} ({voltage_text})。")
                    if self.executor:
                        cmd_frame = self.executor._build_frame(0x02, bytes([0x82]))
                        data_frame = self.executor._build_frame(0x03, bytes([dec_val]))
                        self.serial_worker.write(cmd_frame)
                        QtCore.QThread.msleep(5)
                        self.serial_worker.write(data_frame)
                        self.log_to_textarea(f"[ACTION] 已将新VCOM值 ({voltage_text}) 发送至设备。")
        except Exception as e:
            self.log_to_textarea(f"设置VCOM时出错: {e}", True)

    def _populate_osc_freq_combo(self):
        self.osc_freq_combo.clear()
        freq_map = {
            0: "5 Hz", 1: "10 Hz", 2: "15 Hz", 3: "20 Hz", 4: "30 Hz", 5: "40 Hz",  6: "50 Hz",  7: "60 Hz",
            8: "70 Hz",  9: "80 Hz",  10: "90 Hz",  11: "100 Hz", 12: "110 Hz",   13: "130 Hz", 14: "140 Hz", 15: "150 Hz"
        }
        for dec_val, text in freq_map.items():
            self.osc_freq_combo.addItem(text, userData=dec_val)

    def update_osc_freq_control_from_script(self):
        script_path = self._get_current_init_script_path()
        found = False
        if script_path and os.path.exists(script_path):
            try:
                with open(script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
                found_cmd_line = -1
                for i, line in enumerate(lines):
                    if re.search(r'\bCMD\s+0x30\b', line, re.IGNORECASE): found_cmd_line = i; break
                if found_cmd_line != -1 and found_cmd_line + 1 < len(lines):
                    next_line = lines[found_cmd_line + 1].strip()
                    if next_line.upper().startswith("DATA"):
                        match = re.search(r'0x[0-9a-fA-F]{1,2}', next_line)
                        if match:
                            target_dec_val = int(match.group(0), 16)
                            index = self.osc_freq_combo.findData(target_dec_val)
                            if index != -1: self.osc_freq_combo.setCurrentIndex(index); found = True
            except Exception as e:
                self.log_to_textarea(f"[ERROR] 解析OSC频率时出错: {e}", True)
        is_enabled = found and self.serial_worker is not None
        self.osc_freq_combo.setEnabled(is_enabled)
        self.osc_freq_set_btn.setEnabled(is_enabled)
        if not found: self.osc_freq_combo.setCurrentIndex(-1)

    def handle_set_osc_freq(self):
        script_path = self._get_current_init_script_path()
        if not script_path or not os.path.exists(script_path): return
        selected_index = self.osc_freq_combo.currentIndex()
        if selected_index == -1: return
        dec_val = self.osc_freq_combo.itemData(selected_index)
        freq_text = self.osc_freq_combo.itemText(selected_index)
        new_hex_text = f"0x{dec_val:02X}"
        try:
            with open(script_path, 'r', encoding='utf-8') as f: lines = f.readlines()
            found_cmd_line = -1
            for i, line in enumerate(lines):
                if re.search(r'\bCMD\s+0x30\b', line, re.IGNORECASE): found_cmd_line = i; break
            if found_cmd_line != -1 and found_cmd_line + 1 < len(lines):
                data_line_index = found_cmd_line + 1
                original_data_line = lines[data_line_index]
                if original_data_line.strip().upper().startswith("DATA"):
                    lines[data_line_index] = re.sub(r'0x[0-9a-fA-F]{1,2}', new_hex_text, original_data_line, count=1)
                    with open(script_path, 'w', encoding='utf-8') as f: f.write("".join(lines))
                    self.log_to_textarea(f"[SUCCESS] 脚本OSC频率已更新为 {new_hex_text} ({freq_text})。")
                    if self.executor:
                        cmd_frame = self.executor._build_frame(0x02, bytes([0x30]))
                        data_frame = self.executor._build_frame(0x03, bytes([dec_val]))
                        self.serial_worker.write(cmd_frame)
                        QtCore.QThread.msleep(5)
                        self.serial_worker.write(data_frame)
                        self.log_to_textarea(f"[ACTION] 已将新OSC频率 ({freq_text}) 发送至设备。")
        except Exception as e:
            self.log_to_textarea(f"设置OSC频率时出错: {e}", True)

    def is_any_task_running(self):
        return any(t and t.isRunning() for t in [self.image_thread, self.lut_thread, self.flow_thread, self.multi_image_thread])

    def open_serial(self):
        if self.is_any_task_running(): return
        selected_text = self.port_combo.currentText()
        if not selected_text or "扫描中" in selected_text or "未发现" in selected_text:
            QtWidgets.QMessageBox.warning(self, "错误", "请选择一个有效的串口设备"); return
        port = selected_text
        if "EVK驱动板" in selected_text:
            match = re.search(r'\((\S+)\)', selected_text)
            if match: port = match.group(1)
        baud = int(self.baud_combo.currentText())
        self.serial_thread = QThread(self)
        self.serial_worker = SerialWorker(port, baud)
        self.serial_worker.moveToThread(self.serial_thread)
        self.serial_worker.finished.connect(self.on_serial_connection_lost)
        self.serial_worker.data_received.connect(self.on_data_received_log)
        self.serial_worker.error_occurred.connect(lambda msg: self.log_to_textarea(f"[SERIAL_ERROR] {msg}", True))
        self.executor = ScriptExecutor(self.serial_worker)
        self.executor.log_message.connect(self.log_to_textarea)
        self.serial_thread.started.connect(self.serial_worker.run)
        self.serial_thread.start()
        self.open_btn.setEnabled(False); self.close_btn.setEnabled(True)
        self.log_to_textarea(f"[INFO] 已连接设备: {port} @ {baud}")
        self.update_vcom_control_from_script()
        self.update_osc_freq_control_from_script()

    def close_serial(self):
        if self.image_thread and self.image_thread.isRunning(): self.image_worker.stop()
        if self.lut_thread and self.lut_thread.isRunning(): self.lut_worker.stop()
        if self.flow_thread and self.flow_thread.isRunning(): self.flow_worker.stop()
        if self.multi_image_thread and self.multi_image_thread.isRunning(): self.multi_image_worker.stop()
        if self.executor: self.executor.stop_all_tasks()
        if self.serial_thread and self.serial_thread.isRunning(): self.serial_worker.stop()
        else: self.on_serial_connection_lost()

    def on_serial_connection_lost(self):
        if not self.open_btn.isEnabled():
            self.log_to_textarea("[INFO] 设备已断开连接。")
            self.open_btn.setEnabled(True); self.close_btn.setEnabled(False)
        self.executor = None; self.serial_worker = None; self.serial_thread = None

    def scan_devices(self):
        if self.is_any_task_running(): return
        self.log_to_textarea("[INFO] 正在扫描设备...")
        self.refresh_btn.setEnabled(False)
        self.port_combo.clear(); self.port_combo.addItem("扫描中...")
        self.scanner_thread = QThread(self)
        self.scanner = DeviceScanner()
        self.scanner.moveToThread(self.scanner_thread)
        self.scanner.device_found.connect(self.on_device_found)
        self.scanner.device_found.connect(self.scanner_thread.quit)
        self.scanner_thread.finished.connect(self.scanner.deleteLater)
        self.scanner_thread.finished.connect(lambda: setattr(self, 'scanner_thread', None))
        self.scanner_thread.started.connect(self.scanner.run)
        self.scanner_thread.start()

    def on_device_found(self, found_port, all_ports):
        self.port_combo.clear()
        if not all_ports: self.port_combo.addItem("未发现任何串口")
        else:
            for port in all_ports: self.port_combo.addItem(f"EVK驱动板 ({port})" if port == found_port else port)
        if found_port:
            self.port_combo.setCurrentText(f"EVK驱动板 ({found_port})")
            self.log_to_textarea(f"[SUCCESS] 找到目标设备于 {found_port}！", False)
        else: self.log_to_textarea("[WARN] 未找到目标设备，请检查连接和固件。", False)
        self.refresh_btn.setEnabled(True)

    def _execute_script_by_key(self, script_key):
        if self.is_any_task_running(): return
        if not self.serial_worker or not self.current_profile: return
        scripts = self.current_profile.get("scripts", {})
        relative_script_path = scripts.get(script_key)
        if not relative_script_path:
            self.log_to_textarea(f"[ERROR] 当前Profile '{self.current_profile['ic_name']}' 未定义 '{script_key}' 脚本。", True); return
        profile_root = self.current_profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        self.log_to_textarea(f"[ACTION] 请求: 执行 '{script_key}' 脚本 ({os.path.basename(absolute_script_path)})...")
        self.executor.run_script(absolute_script_path)

    def handle_run_init_from_combo(self):
        if self.is_any_task_running(): return
        if not self.serial_worker or not self.current_profile: return
        selected_init_name = self.init_combo.currentText()
        if not selected_init_name: return
        init_map = self.current_profile.get("initializations")
        if init_map and selected_init_name in init_map:
            relative_script_path = init_map.get(selected_init_name)
        else: relative_script_path = self.current_profile.get("init_script")
        if not relative_script_path: return
        profile_root = self.current_profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        self.log_to_textarea(f"[ACTION] 请求: 执行初始化 '{selected_init_name}' ({os.path.basename(absolute_script_path)})...")
        self.executor.run_script(absolute_script_path)

    def handle_edit_init_script(self):
        if not self.current_profile: return
        selected_init_name = self.init_combo.currentText()
        if not selected_init_name or "无初始化脚本" in selected_init_name: return
        init_map = self.current_profile.get("initializations", {})
        relative_script_path = init_map.get(selected_init_name)
        if not relative_script_path:
            if selected_init_name == "Default Init":
                relative_script_path = self.current_profile.get("init_script")
            else: return
        profile_root = self.current_profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        if not os.path.exists(absolute_script_path): return
        try:
            with open(absolute_script_path, 'r', encoding='utf-8') as f: script_content = f.read()
            dialog = QtWidgets.QDialog(self)
            dialog.setWindowTitle(f"编辑脚本: {os.path.basename(absolute_script_path)}")
            dialog.setMinimumSize(500, 600)
            layout = QtWidgets.QVBoxLayout(dialog)
            text_edit = QtWidgets.QTextEdit()
            text_edit.setFont(QtGui.QFont("Courier New", 10))
            text_edit.setText(script_content)
            button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
            button_box.accepted.connect(dialog.accept)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(text_edit)
            layout.addWidget(button_box)
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                new_content = text_edit.toPlainText()
                with open(absolute_script_path, 'w', encoding='utf-8') as f: f.write(new_content)
                self.log_to_textarea(f"[SUCCESS] 成功保存脚本: {os.path.basename(absolute_script_path)}", False)
                self.update_vcom_control_from_script()
                self.update_osc_freq_control_from_script()
        except Exception as e:
            self.log_to_textarea(f"打开或保存脚本时出错: {e}", True)

    def handle_update_lut_from_combo(self):
        if self.is_any_task_running(): return
        if not self.serial_worker or not self.current_profile: return
        selected_lut_name = self.lut_combo.currentText()
        if not selected_lut_name or selected_lut_name == "无预设Lut": return
        lut_map = self.current_profile.get("luts", {})

        # --- [ 修改此部分代码 ] ---
        lut_info = lut_map.get(selected_lut_name)
        # 检查是否获取到字典，并且字典里有 "variable" 键
        if not isinstance(lut_info, dict) or "variable" not in lut_info:
             self.log_to_textarea(f"[ERROR] 无法从JSON获取波形 '{selected_lut_name}' 的变量名。", True)
             return
        c_array_name = lut_info.get("variable") 
        # --- [ 修改结束 ] ---


        lut_source_filename = self.current_profile.get("lut_source_file")
        profile_root = self.current_profile.get('__root_path__')
        if not all([c_array_name, lut_source_filename, profile_root]): return
        try:
            lut_source_path = os.path.join(profile_root, lut_source_filename)
            with open(lut_source_path, 'r', encoding='utf-8') as f: full_text = f.read()
            pattern = re.compile(rf'const\s+(unsigned\s+char|uint8_t)\s+{c_array_name}\s*\[[^\]]*\]\s*=\s*{{(.*?)\}};', re.DOTALL)
            match = pattern.search(full_text)
            if not match: return
            array_content = match.group(2)
            hex_values = re.findall(r'0x([0-9a-fA-F]{1,2})', array_content)
            lut_data = bytes([int(val, 16) for val in hex_values])
        except Exception as e:
            self.log_to_textarea(f"读取或解析Lut文件时出错: {e}", True); return
        script_key = "update_lut"
        scripts = self.current_profile.get("scripts", {})
        relative_script_path = scripts.get(script_key)
        if not relative_script_path: return
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        self.start_lut_update_task(absolute_script_path, lut_data)

    def handle_delete_lut(self):
        if not self.current_profile: return
        selected_lut_name = self.lut_combo.currentText()
        if not selected_lut_name or selected_lut_name == "无预设Lut": return
        reply = QtWidgets.QMessageBox.question(self, '确认删除', f"您确定要删除波形 '{selected_lut_name}' 吗？\n此操作将从.json和.txt文件中永久移除该波形，且无法撤销。", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No: return
        try:
            lut_map = self.current_profile.get("luts", {})

             # --- [ 修改此部分代码 ] ---
            lut_info = lut_map.get(selected_lut_name)
            if not isinstance(lut_info, dict) or "variable" not in lut_info:
                 # 如果json结构不对，可能无法获取变量名，但我们仍然尝试删除json条目
                 c_array_name = None 
                 self.log_to_textarea(f"[WARN] 无法获取波形 '{selected_lut_name}' 的变量名，将只尝试删除JSON条目。", True)
            else:
                 c_array_name = lut_info.get("variable")
            # --- [ 修改结束 ] ---


            profile_root = self.current_profile.get('__root_path__')
            lut_source_filename = self.current_profile.get("lut_source_file")
            if not all([c_array_name, profile_root, lut_source_filename]): raise ValueError("Profile配置信息不完整。")
            json_path = self._find_profile_json(profile_root)
            if not json_path or not os.path.exists(json_path): raise FileNotFoundError(f"在 '{profile_root}' 中未找到.json配置文件。")
            with open(json_path, 'r+', encoding='utf-8') as f:
                profile_data = json.load(f)
                if "luts" in profile_data and selected_lut_name in profile_data["luts"]:
                    del profile_data["luts"][selected_lut_name]
                    f.seek(0); f.truncate()
                    json.dump(profile_data, f, indent=4, ensure_ascii=False)
            lut_source_path = os.path.join(profile_root, lut_source_filename)
            if os.path.exists(lut_source_path):
                with open(lut_source_path, 'r', encoding='utf-8') as f: lines = f.readlines()
                start_index, end_index = -1, -1; brace_level = 0; in_block = False
                for i, line in enumerate(lines):
                    if not in_block and c_array_name in line and "const" in line and "=" in line:
                        start_index = i; in_block = True
                    if in_block:
                        brace_level += line.count('{')
                        brace_level -= line.count('}')
                        if brace_level == 0 and ';' in line:
                            end_index = i; break
                if start_index != -1 and end_index != -1:
                    cleaned_start_index = start_index
                    for i in range(start_index - 1, -1, -1):
                        line_content = lines[i].strip()
                        if line_content == "" or line_content.startswith("//"): cleaned_start_index = i
                        else: break
                    del lines[cleaned_start_index : end_index + 1]
                    with open(lut_source_path, 'w', encoding='utf-8') as f: f.write("".join(lines))
            # 用这一行替换上面那几行：
            self.refresh_ui_after_profile_change()
        except Exception as e:
            self.log_to_textarea(f"删除波形时发生错误: {e}", True)
            
    def _find_profile_json(self, directory):
        for filename in os.listdir(directory):
            if filename.endswith(".json"): return os.path.join(directory, filename)
        return None       

    # (在 MainWindow 类中)
    def handle_open_waveform_editor(self):
        # 1. 检查是否有 Profile
        if self.is_any_task_running(): return # 如果有任务在运行，不允许打开编辑器
        if not self.current_profile: 
             QtWidgets.QMessageBox.warning(self, "提示", "请先选择一个Profile。")
             return
             
        # 2. 获取 Profile 相关路径和信息
        profile_root = self.current_profile.get('__root_path__')
        lut_source_filename = self.current_profile.get("lut_source_file")
        lut_data = b'' # 默认空数据
        current_waveform_info = None # 默认没有编辑现有波形
        
        # --- [ 新增：记住当前刷新模式 开始 ] ---
        # 记录当前选中的刷新模式单选按钮的对象名称
        current_refresh_mode_object_name = None
        # 查找哪个单选按钮被选中
        if self.rb_refresh_gc.isChecked(): #
            current_refresh_mode_object_name = self.rb_refresh_gc.objectName() 
            # 如果按钮还没有 objectName (通常在 UI 文件中设置，但以防万一)
            if not current_refresh_mode_object_name: 
                 self.rb_refresh_gc.setObjectName("rb_refresh_gc") # 手动设置
                 current_refresh_mode_object_name = "rb_refresh_gc"
        elif self.rb_refresh_4gray.isChecked(): #
            current_refresh_mode_object_name = self.rb_refresh_4gray.objectName()
            if not current_refresh_mode_object_name:
                 self.rb_refresh_4gray.setObjectName("rb_refresh_4gray")
                 current_refresh_mode_object_name = "rb_refresh_4gray"
        elif self.rb_refresh_partial.isChecked(): #
            current_refresh_mode_object_name = self.rb_refresh_partial.objectName()
            if not current_refresh_mode_object_name:
                 self.rb_refresh_partial.setObjectName("rb_refresh_partial")
                 current_refresh_mode_object_name = "rb_refresh_partial"
        # 打印调试信息 (可选)
        # print(f"DEBUG: Storing refresh mode button name: {current_refresh_mode_object_name}") 
        # --- [ 新增：记住当前刷新模式 结束 ] ---
        
        # 3. 尝试加载当前选中的预设波形数据 (如果选中了有效波形)
        try:
            selected_lut_name = self.lut_combo.currentText() #
            # 检查选中的不是提示信息，并且 lut 源文件名存在
            if selected_lut_name and "无" not in selected_lut_name and lut_source_filename:
                lut_map = self.current_profile.get("luts", {})
                lut_info = lut_map.get(selected_lut_name) # 获取波形信息字典
                c_array_name = None
                # 检查是否是新的字典结构，并且包含 "variable" 键
                if isinstance(lut_info, dict):
                    c_array_name = lut_info.get("variable")
                    
                if c_array_name: # 如果成功获取到 C 变量名
                    lut_source_path = os.path.join(profile_root, lut_source_filename)
                    # 检查 C 源文件是否存在
                    if os.path.exists(lut_source_path):
                        with open(lut_source_path, 'r', encoding='utf-8') as f: 
                            full_text = f.read()
                        # 使用正则表达式查找对应的 C 数组定义
                        pattern = re.compile(
                            # 匹配 "const unsigned char VAR_NAME [...] = { ... };" 或 "const uint8_t VAR_NAME [...] = { ... };"
                            rf'const\s+(?:unsigned\s+char|uint8_t)\s+{re.escape(c_array_name)}\s*\[[^\]]*\]\s*=\s*{{(.*?)\}};', 
                            re.DOTALL # re.DOTALL 让 '.' 可以匹配换行符
                        )
                        match = pattern.search(full_text)
                        if match: # 如果找到匹配
                            array_content = match.group(1) # 获取花括号内的内容
                            # 提取所有十六进制数值 (0xXX)
                            hex_values = re.findall(r'0x([0-9a-fA-F]{1,2})', array_content)
                            # 将十六进制字符串转换为字节数据
                            lut_data = bytes([int(val, 16) for val in hex_values])
                            # 记录当前正在编辑的波形信息
                            current_waveform_info = { "name": selected_lut_name, "var_name": c_array_name }
                        else:
                            self.log_to_textarea(f"[WARN] 在文件 '{lut_source_filename}' 中未找到变量 '{c_array_name}' 的 C 数组定义。")
                    else:
                         self.log_to_textarea(f"[WARN] Lut 源文件 '{lut_source_filename}' 未找到。")
                else:
                    self.log_to_textarea(f"[WARN] 无法从 JSON 获取波形 '{selected_lut_name}' 的变量名 (variable key)。")
        except Exception as e:
            # 捕获加载过程中可能出现的任何异常
            self.log_to_textarea(f"[ERROR] 加载预设波形 '{selected_lut_name}' 时发生错误: {e}", True)
            
        # 4. 创建并显示波形编辑器对话框
        dialog = WaveformEditorDialog(
            profile=self.current_profile, 
            lut_data=lut_data, # 传入加载的数据 (可能是空的)
            current_waveform_info=current_waveform_info, # 传入正在编辑的波形信息 (可能是 None)
            parent=self
        )
        # 连接信号，当编辑器点击 "应用并更新到设备" 时触发
        dialog.lut_data_ready.connect(self.on_manual_lut_data_ready) 
        
        # 5. 显示对话框 (阻塞主窗口)，并保存对话框的关闭方式 (Accept 或 Reject)
        dialog_result = dialog.exec_() 

        # 6. 获取编辑器最终使用的波形名称 (用于刷新后重新选中)
        name_to_select = dialog.final_waveform_name 
        
        # 7. 刷新主窗口UI (重新加载 Profile, 更新 Lut 列表等)
        #    这步会重置刷新模式单选按钮到默认的 GC
        self.refresh_ui_after_profile_change(new_name_to_select=name_to_select)
        
        # --- [ 新增：恢复刷新模式 开始 ] ---
        # 检查之前是否成功记录了模式按钮的 objectName
        if current_refresh_mode_object_name:
             # 使用 findChild 通过 objectName 查找对应的 QRadioButton 控件
             button_to_restore = self.findChild(QtWidgets.QRadioButton, current_refresh_mode_object_name)
             if button_to_restore: # 如果找到了按钮
                  # 先阻止按钮状态改变时发出信号，避免触发两次 _on_refresh_mode_changed
                  button_to_restore.blockSignals(True) 
                  # 将按钮状态设置为选中
                  button_to_restore.setChecked(True) 
                  # 恢复信号发送
                  button_to_restore.blockSignals(False) 
                  
                  # 打印调试信息 (可选)
                  # print(f"DEBUG: Restored refresh mode to: {current_refresh_mode_object_name}")
                  
                  # 手动调用一次 _on_refresh_mode_changed，
                  # 确保 Lut 列表和目标模式下拉框根据恢复后的模式正确更新
                  self._on_refresh_mode_changed() 
             # else: # 调试信息 (可选)
                  # print(f"DEBUG: Could not find button with name: {current_refresh_mode_object_name}")
        # --- [ 新增：恢复刷新模式 结束 ] ---
          
    def refresh_ui_after_profile_change(self, new_name_to_select=None):
        """
        在 Profile 相关内容（如Lut）发生变化后，刷新UI并尝试恢复之前的选择。
        (已更新为使用 QMenu 逻辑)
        """
        current_ic_name = None
        if self.current_profile:
            current_ic_name = self.current_profile.get("ic_name")

        # 1. 重新加载所有 profiles 并重建菜单
        # (这也会重置UI到 "---请选择Profile---")
        self._load_profiles() 

        if not current_ic_name:
            return # 之前没有选中, 直接返回

        # 2. 查找对应的 Action
        action_to_trigger = None
        # 遍历所有子菜单 (QMenu)
        for menu in self.profile_menu.findChildren(QtWidgets.QMenu):
            # 遍历菜单中的所有动作 (QAction)
            for action in menu.actions():
                if action.data() == current_ic_name:
                    action_to_trigger = action
                    break
            if action_to_trigger:
                break
        
        if action_to_trigger:
            # 3. 如果找到，手动触发选中逻辑
            self._on_profile_action_selected(action_to_trigger)
        
            # 4. 恢复Lut选择
            if new_name_to_select:
                new_lut_index = self.lut_combo.findText(new_name_to_select)
                if new_lut_index != -1:
                    self.lut_combo.setCurrentIndex(new_lut_index)
        else:
            self.log_to_textarea(f"[WARN] 刷新UI：未在菜单中找到之前的IC {current_ic_name}", True)
            
    def on_manual_lut_data_ready(self, lut_data):
        script_key = "update_lut"; scripts = self.current_profile.get("scripts", {}); relative_script_path = scripts.get(script_key)
        if not relative_script_path: return
        profile_root = self.current_profile.get('__root_path__'); absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        self.start_lut_update_task(absolute_script_path, lut_data)

    def start_lut_update_task(self, script_path, lut_data):
        if self.is_any_task_running(): return
        self.lut_thread = QThread(self)
        self.lut_worker = LutUpdateWorker(self.serial_worker, script_path, lut_data)
        self.lut_worker.moveToThread(self.lut_thread)
        self.lut_worker.finished.connect(self.on_lut_task_finished)
        self.lut_worker.finished.connect(self.lut_thread.quit)
        self.lut_thread.finished.connect(self.lut_worker.deleteLater)
        self.lut_thread.finished.connect(lambda: setattr(self, 'lut_thread', None))
        self.lut_thread.started.connect(self.lut_worker.run)
        self.set_controls_enabled(False)
        self.lut_thread.start()

    def on_lut_task_finished(self):
        self.set_controls_enabled(True)
        self.lut_worker = None
    
    def _start_fill_task(self, fill_mode):
        if self.is_any_task_running(): return
        if not self.serial_worker or not self.current_profile: return

        # --- [ 核心修改：根据单选框决定脚本 ] ---
        
        script_key = None
        is_partial_mode = False
        
        if self.rb_refresh_gc.isChecked():
            script_key = "display_full_gc"
        elif self.rb_refresh_4gray.isChecked():
            # "刷白/刷黑" 理论上不支持4灰阶，但如果选中，我们强制使用 GC
            # 只有当 Profile 只有 4灰阶 而没有 GC 时才使用 4灰阶
            if "display_full_gc" in self.current_profile.get("scripts", {}):
                 script_key = "display_full_gc"
            else:
                 script_key = "display_4gray" # 备用
        elif self.rb_refresh_partial.isChecked():
            script_key = "display_partial"
            is_partial_mode = True # 激活局刷逻辑

        if not script_key:
            QtWidgets.QMessageBox.warning(self, "错误", f"未选择有效的刷新模式。")
            return

        scripts = self.current_profile.get("scripts", {})
        relative_script_path = scripts.get(script_key)
        
        if not relative_script_path:
            QtWidgets.QMessageBox.warning(self, "脚本缺失", f"当前Profile中未定义 '{script_key}' 脚本。")
            return
            
        profile_root = self.current_profile.get('__root_path__')
        absolute_script_path = os.path.abspath(os.path.join(profile_root, relative_script_path))
        if not os.path.exists(absolute_script_path):
             QtWidgets.QMessageBox.warning(self, "脚本未找到", f"脚本文件不存在: {absolute_script_path}")
             return

        # --- [ 核心修改：数据生成器 ] ---
        
        res = self.current_profile.get("resolution", {}); width, height = res.get("width"), res.get("height")
        if not width or not height: return

        def fill_data_generator():
            # 1. 生成 "新数据" (刷白/刷黑/网格)
            total_bytes = width * height // 8
            new_bytes_data = None
            if fill_mode == 'white': new_bytes_data = bytes([0xFF]) * total_bytes
            elif fill_mode == 'black': new_bytes_data = bytes([0x00]) * total_bytes
            elif fill_mode == 'grid':
                bytes_per_row = width // 8; row_55, row_aa = bytes([0x55]) * bytes_per_row, bytes([0xAA]) * bytes_per_row
                new_bytes_data = b''.join(row_55 if i % 2 == 0 else row_aa for i in range(height))
            
            if new_bytes_data is None: return None
            
            # 2. 根据模式决定返回内容
            if is_partial_mode:
                # --- 局刷逻辑 (0x10h + 0x13h) ---
                old_bytes_data = self.last_image_bytes
                if old_bytes_data is None:
                    # 第一次局刷, 用 0xFF 填充
                    old_bytes_data = bytearray([0xFF] * total_bytes)
                    self.log_to_textarea("[INFO] 首次局刷，旧数据(0x10h)自动填充 0xFF。", False)
                
                # 更新缓存，为下一次局刷做准备
                self.last_image_bytes = new_bytes_data
                
                # 返回 (旧数据, 新数据) 元组
                return (old_bytes_data, new_bytes_data)
            else:
                # --- 全刷逻辑 ---
                
                # 更新缓存，为下一次局刷做准备
                self.last_image_bytes = new_bytes_data
                
                # 只返回新数据
                return new_bytes_data
        
        # --- [ 修改结束 ] ---

        task_name = {'white': '刷白全屏', 'black': '刷黑全屏', 'grid': '刷新网格'}.get(fill_mode)
        # _start_display_task 已经支持接收 (old_data, new_data) 元组
        self._start_display_task(absolute_script_path, fill_data_generator, task_name)

    def _start_display_task(self, script_path, data_generator, task_name):
        if data_generator is None: return
        image_data = data_generator()
        if image_data is None: return
        self.image_thread = QThread(self)
        self.image_worker = DisplayWorker(self.serial_worker, script_path, lambda: image_data, task_name)
        self.image_worker.moveToThread(self.image_thread)
        self.image_worker.finished.connect(self.on_display_task_finished)
        self.image_worker.progress.connect(self.upload_progress_bar.setValue)
        self.image_worker.log_message.connect(self.log_to_textarea)
        self.image_worker.finished.connect(self.image_thread.quit)
        self.image_thread.finished.connect(self.image_worker.deleteLater)
        self.image_thread.finished.connect(lambda: setattr(self, 'image_thread', None))
        self.image_thread.started.connect(self.image_worker.run)
        self.set_controls_enabled(False)
        self.upload_progress_bar.setValue(0)
        self.image_thread.start()

    def on_display_task_finished(self, success, message):
        if success: self.log_to_textarea(f"[SUCCESS] {message}", False); self.upload_progress_bar.setValue(100)
        else: self.log_to_textarea(f"[ERROR] {message}", True); self.upload_progress_bar.setValue(0)
        self.set_controls_enabled(True) 
        self.is_task_paused = False
        self.pause_resume_btn.setText("暂停")
        self.image_worker = None
        self.multi_image_worker = None

    def on_data_received_log(self, data: bytes):
        try:
            printable_bytes = bytearray(b for b in data if 32 <= b <= 126 or b in [10, 13])
            if printable_bytes:
                text = printable_bytes.decode('ascii').strip()
                if text and "EPD_BOARD" not in text: self.log_to_textarea(text)
        except Exception: pass
        
    def handle_pause_resume(self):
        if not self.multi_image_worker or not self.multi_image_thread.isRunning(): return
        self.is_task_paused = not self.is_task_paused
        if self.is_task_paused:
            self.multi_image_worker.pause()
            self.pause_resume_btn.setText("继续")
            self.log_to_textarea("[ACTION] 任务已暂停。")
        else:
            self.multi_image_worker.resume()
            self.pause_resume_btn.setText("暂停")
            self.log_to_textarea("[ACTION] 任务已继续。")
            
    def log_to_textarea(self, message, is_error=False):
        self.text_area.append(message)

    

    # 这是 _load_profiles 的完整、正确版本

    def _load_profiles(self):
        
        # 1. 获取路径 (utils 会自动返回自定义路径或默认路径)
        user_profiles_dir = utils.get_user_data_path("profiles")
        #utils.log_message(f"--- DEBUG: User profiles directory (target): {user_profiles_dir}")

        # 2. 检查这个路径是否是“默认路径”
        default_path = os.path.join(utils.get_app_base_path(), "profiles")
        is_default_path = (os.path.normpath(user_profiles_dir) == os.path.normpath(default_path))
        #utils.log_message(f"--- DEBUG: Is default path? {is_default_path}")

        # 3. 检查路径是否存在
        if not os.path.exists(user_profiles_dir):
            #utils.log_message(f"--- DEBUG: User profiles not found at target path.")
            
            if is_default_path:
                # --- 情况A：默认路径 且 首次运行 ---
                # 这是我们的“解压”逻辑
                #utils.log_message(f"--- DEBUG: Attempting first-run extraction to default path...")
                try:
                    bundle_profiles_dir = utils.get_bundle_path("profiles")
                    #utils.log_message(f"--- DEBUG: Bundled profiles (source): {bundle_profiles_dir}")
                    
                    if not os.path.exists(bundle_profiles_dir):
                        #utils.log_message(f"--- DEBUG: FATAL - Bundled profiles not found at source!")
                        self.log_to_textarea("[ERROR] 找不到内置Profiles, 无法初始化。")
                        self._build_profile_menu()
                        return

                    # 执行复制
                    shutil.copytree(bundle_profiles_dir, user_profiles_dir)
                    #utils.log_message(f"--- DEBUG: Successfully extracted profiles to user directory.")
                    
                    # 提示用户重启
                    QMessageBox.information(self, 
                                            "初始化成功", 
                                            "首次运行初始化成功。\n\n"
                                            "配置文件已生成在程序目录，请点击 'OK' 退出，然后重新启动程序。")
                    
                    sys.exit(0) # 安全退出
                    
                except Exception as e:
                    #utils.log_message(f"--- DEBUG: FATAL - Failed to extract profiles: {e}")
                    self.log_to_textarea(f"[ERROR] 提取Profiles失败: {e}")
                    self._build_profile_menu()
                return # 退出函数

            else:
                # --- 情况B：自定义路径 且 路径不存在 ---
                # 用户设置了一个无效的自定义路径
                #utils.log_message(f"--- DEBUG: Custom path does not exist.")
                self.log_to_textarea(f"[ERROR] 自定义路径不存在: {user_profiles_dir}")
                QMessageBox.warning(self,
                    "路径错误",
                    f"自定义的 'profiles' 路径不存在：\n{user_profiles_dir}\n\n"
                    "请在 '文件' -> '设置 Profile 路径...' 中重新指定。")
                self._build_profile_menu() # 构建空菜单
                return # 退出函数

        # --- 情况C：路径存在 (无论是自定义的还是默认的) ---
        #utils.log_message(f"--- DEBUG: User profiles directory found. Loading...")
        
        # 4. (所有情况) 从 *用户* 路径加载
        self.profiles_dir = user_profiles_dir
        
        # 5. 清空数据结构
        self.profiles.clear()
        self.profiles_by_size = {} 

        # 6. 遍历 Profiles 目录加载 JSON 文件
        try:
            for root, _, files in os.walk(self.profiles_dir):
                for filename in files:
                    if filename.endswith(".json"):
                        filepath = os.path.join(root, filename)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f: 
                                profile_data = json.load(f)
                                
                            if "ic_name" in profile_data and "inch" in profile_data:
                                ic_name = profile_data["ic_name"]
                                inch_size = str(profile_data["inch"])
                                
                                profile_data['__root_path__'] = root
                                self.profiles[ic_name] = profile_data
                                
                                if inch_size not in self.profiles_by_size:
                                    self.profiles_by_size[inch_size] = []
                                self.profiles_by_size[inch_size].append(ic_name)
                                
                        except Exception as e:
                            self.log_to_textarea(f"[ERROR] 加载Profile '{filepath}' 失败: {e}")
        except Exception as e:
            utils.log_message(f"[ERROR] 遍历 Profiles 目录失败: {e}")
            self.log_to_textarea(f"[ERROR] 遍历 Profiles 目录失败: {e}")

        # 7. 构建菜单
        self._build_profile_menu()

        # 8. 重置选择和信息显示
        self.current_profile = None
        self.profile_select_btn.setText("---请选择Profile---")
        self.profile_info_label.setText("分辨率: N/A")
        self.screen_size_label.setText("尺寸: N/A")
        
        # 9. 清空并禁用相关控件
        self.update_lut_combo()
        self.update_init_combo()
        self.update_flows_ui()
        self.rb_refresh_gc.setEnabled(False)
        self.rb_refresh_4gray.setEnabled(False)
        self.rb_refresh_partial.setEnabled(False)
        self.rb_refresh_gc.setChecked(True)

    def _build_profile_menu(self):
        """
        根据 self.profiles_by_size 构建二级菜单
        """
        self.profile_menu.clear() # 清空旧菜单
        
        # 按尺寸数值排序
        sorted_sizes = sorted(self.profiles_by_size.keys(), key=lambda x: float(x))
        
        if not sorted_sizes:
            self.profile_menu.addAction("未找到Profiles").setEnabled(False)
            return

        # 遍历尺寸 (第一级菜单)
        for size in sorted_sizes:
            # f"{size}\" ({len(self.profiles_by_size[size])})" # 也可以带数量
            size_menu = self.profile_menu.addMenu(f"{size}\"") 

            # 遍历该尺寸下的 IC (第二级菜单)
            ic_names = sorted(self.profiles_by_size[size])
            for ic_name in ic_names:
                # QAction 是菜单项
                action = QtWidgets.QAction(ic_name, self)
                action.setData(ic_name) # 关键：将 ic_name 存入 action
                size_menu.addAction(action)

    def show_profile_menu(self):
        """
        在按钮下方显示菜单
        """
        # 在按钮的左下角弹出菜单
        self.profile_menu.popup(self.profile_select_btn.mapToGlobal(
            QtCore.QPoint(0, self.profile_select_btn.height())
        ))

    def _on_profile_action_selected(self, action):
        """
        当用户在菜单中选择了一个 IC (QAction) 时触发
        """
        ic_name = action.data() # 获取存入的 ic_name
        if not ic_name or ic_name not in self.profiles:
            self.log_to_textarea(f"[ERROR] 菜单项 {ic_name} 无效", True)
            return

        self.current_profile = self.profiles[ic_name]
        
        # 1. 更新UI上的显示
        self.profile_select_btn.setText(ic_name) # 更新按钮文本
        res = self.current_profile.get("resolution", {})
        width, height = res.get("width", "N/A"), res.get("height", "N/A")
        self.profile_info_label.setText(f"分辨率: {width}x{height}")
        self.screen_size_label.setText(f"尺寸: {self.current_profile.get('inch', '')}\"")

        # 2. 更新所有依赖 Profile 的UI
        self.process_and_preview_image()
        self.update_lut_combo()
        self.update_init_combo()
        self.update_flows_ui() # 更新流程按钮

        # 3. 动态启用/禁用刷新模式 (同旧逻辑)
        scripts = self.current_profile.get("scripts", {})
        self.rb_refresh_gc.setEnabled("display_full_gc" in scripts)
        self.rb_refresh_4gray.setEnabled("display_4gray" in scripts)
        self.rb_refresh_partial.setEnabled("display_partial" in scripts)
        
        # 4. 设置默认选中 GC 并触发联动
        if self.rb_refresh_gc.isEnabled():
             self.rb_refresh_gc.setChecked(True) 
        elif self.rb_refresh_partial.isEnabled():
             self.rb_refresh_partial.setChecked(True)
        elif self.rb_refresh_4gray.isEnabled():
             self.rb_refresh_4gray.setChecked(True)
        else: 
             self.rb_refresh_gc.setChecked(True) 
             
        self._on_refresh_mode_changed() # 触发联动更新

    


    def update_flows_ui(self):
        for i in reversed(range(self.flows_layout.count())): 
            widget = self.flows_layout.itemAt(i).widget()
            if widget: widget.setParent(None)
        if not self.current_profile: return
        flows = self.current_profile.get("flows", {})
        for flow_key, flow_data in flows.items():
            btn = QtWidgets.QPushButton(flow_data.get("name", flow_key))
            btn.clicked.connect(lambda checked, steps=flow_data.get("steps", []): self.handle_run_flow(steps))
            self.flows_layout.addWidget(btn)

    def handle_run_flow(self, steps):
        if self.is_any_task_running(): return
        if not self.serial_worker: return
        self.flow_thread = QThread(self)
        self.flow_worker = FlowWorker(self.serial_worker, self.current_profile, steps)
        self.flow_worker.moveToThread(self.flow_thread)
        self.flow_worker.finished.connect(self.on_flow_task_finished)
        self.flow_worker.log_message.connect(self.log_to_textarea)
        self.flow_worker.finished.connect(self.flow_thread.quit)
        self.flow_worker.finished.connect(self.flow_worker.deleteLater)
        self.flow_thread.finished.connect(lambda: setattr(self, 'flow_thread', None))
        self.flow_thread.started.connect(self.flow_worker.run)
        self.set_controls_enabled(False)
        self.flow_thread.start()

    def on_flow_task_finished(self, success, message):
        if success: self.log_to_textarea(f"[SUCCESS] {message}", False)
        else: self.log_to_textarea(f"[ERROR] {message}", True)
        self.set_controls_enabled(True)
        self.flow_worker = None

    def update_init_combo(self):
        self.init_combo.clear(); enabled = False
        if self.current_profile:
            init_options = self.current_profile.get("initializations")
            if init_options and isinstance(init_options, dict):
                for display_name in init_options.keys(): self.init_combo.addItem(display_name)
                enabled = True
            else:
                legacy_init_script = self.current_profile.get("init_script")
                if legacy_init_script: self.init_combo.addItem("Default Init"); enabled = True
        if not enabled: self.init_combo.addItem("无初始化脚本")
        self.init_combo.setEnabled(enabled)
        self.run_init_btn.setEnabled(enabled)
        self.edit_init_btn.setEnabled(enabled)
        self.update_vcom_control_from_script()
        self.update_osc_freq_control_from_script()

    # (替换旧的 update_lut_combo 函数)
    def update_lut_combo(self):
        self.lut_combo.clear() #
        
        # 1. 确定当前选中的刷新模式
        target_mode = "gc" # 默认全局刷新
        if self.rb_refresh_4gray.isChecked(): #
            target_mode = "4gray"
        elif self.rb_refresh_partial.isChecked(): #
            target_mode = "partial"

        # 2. 检查 Profile 和 "luts" 字段
        if not self.current_profile or "luts" not in self.current_profile:
            self.lut_combo.addItem("无预设Lut")
            self.lut_combo.setEnabled(False)
            self.update_lut_btn.setEnabled(False) #
            self.edit_lut_btn.setEnabled(False) #
            self.delete_lut_btn.setEnabled(False) #
            return

        # 3. 过滤并添加匹配的波形
        lut_options = self.current_profile["luts"]
        found_luts = False
        # 遍历 JSON 中定义的所有 luts
        for display_name in sorted(lut_options.keys()):
            lut_info = lut_options[display_name]
            # 检查是否是新的字典结构，并且 "mode" 标签匹配当前选中的刷新模式
            if isinstance(lut_info, dict) and lut_info.get("mode") == target_mode:
                self.lut_combo.addItem(display_name) # 添加到下拉列表
                found_luts = True

        # 4. 如果没有找到匹配的波形，显示提示
        if not found_luts:
            self.lut_combo.addItem(f"无 {target_mode} 模式波形")
            
        # 5. 根据是否找到波形，设置相关按钮的启用状态
        self.lut_combo.setEnabled(found_luts)
        self.update_lut_btn.setEnabled(found_luts) #
        self.edit_lut_btn.setEnabled(True) # 编辑按钮通常保持可用，允许创建新波形
        self.delete_lut_btn.setEnabled(found_luts) #
            
    def handle_show_help(self):
        dialog = UserGuideDialog(self)
        dialog.exec_()

    def closeEvent(self, event):
        self.log_to_textarea("[SYSTEM] 正在关闭应用程序...")
        self.close_serial()
        event.accept()
