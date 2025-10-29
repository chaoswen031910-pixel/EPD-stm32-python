import sys
import os
import json
import re
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import pyqtSignal

# 假设这些模块在您的项目中是可用的
from lut_formats import get_lut_handler

# --- [ 新增辅助类 开始 ] ---
class SaveWaveformDialog(QtWidgets.QDialog):
    """用于 '另存为' 时输入名称并选择模式的对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("另存为新波形")
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # 1. 名称输入
        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(QtWidgets.QLabel("波形显示名称:"))
        self.name_edit = QtWidgets.QLineEdit()
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # 2. 模式选择
        self.mode_group = QtWidgets.QGroupBox("选择波形模式:")
        mode_layout = QtWidgets.QHBoxLayout(self.mode_group)
        self.rb_gc = QtWidgets.QRadioButton("全局刷新 (GC)")
        self.rb_partial = QtWidgets.QRadioButton("局部刷新 (Partial)")
        self.rb_4gray = QtWidgets.QRadioButton("4灰阶刷新")
        mode_layout.addWidget(self.rb_gc)
        mode_layout.addWidget(self.rb_partial)
        mode_layout.addWidget(self.rb_4gray)
        self.rb_gc.setChecked(True) # 默认选中 GC
        layout.addWidget(self.mode_group)
        
        # 3. 按钮
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_save_details(self):
        """返回用户输入的名称和选择的模式"""
        name = self.name_edit.text().strip()
        mode = "gc" # 默认
        if self.rb_partial.isChecked():
            mode = "partial"
        elif self.rb_4gray.isChecked():
            mode = "4gray"
        return name, mode
# --- [ 新增辅助类 结束 ] ---


class WaveformEditorDialog(QtWidgets.QDialog):
    lut_data_ready = pyqtSignal(bytes)

    def __init__(self, profile, lut_data=b'', current_waveform_info=None, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.ic_name = self.profile.get("ic_name", "未知IC")
        self.current_waveform_info = current_waveform_info
        
        self.final_waveform_name = self.current_waveform_info['name'] if self.current_waveform_info else None

        if self.current_waveform_info:
            self.setWindowTitle(f"参数化波形编辑器 - 正在编辑: {self.current_waveform_info['name']}")
        else:
            self.setWindowTitle(f"参数化波形编辑器 - {self.ic_name}")
            
        self.resize(1400, 600)
        
        try:
            self.handler = get_lut_handler(self.profile)
        except (ValueError, NotImplementedError) as e:
            QtWidgets.QMessageBox.critical(self, "错误", str(e))
            QtCore.QTimer.singleShot(0, self.reject)
            return

        self.setup_ui()
        
        if lut_data:
            self.populate_ui_from_data(lut_data)
            # 同时也编译一下，以获取数据长度，为重命名做准备
            self.compile_waveform()

    def setup_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        scroll_area = QtWidgets.QScrollArea(); scroll_area.setWidgetResizable(True)
        main_layout.addWidget(scroll_area, 1)
        container_widget = QtWidgets.QWidget(); scroll_area.setWidget(container_widget)
        grid = QtWidgets.QGridLayout(container_widget); grid.setSpacing(5)

        self.handler.build_ui(grid)
        
        result_group = QtWidgets.QGroupBox("编译结果")
        result_layout = QtWidgets.QVBoxLayout(result_group)
        self.result_text = QtWidgets.QTextEdit(); self.result_text.setReadOnly(True); self.result_text.setFontFamily("Courier")
        self.result_text.setPlaceholderText("调整参数后，点击“编译波形”...")
        result_layout.addWidget(self.result_text)
        main_layout.addWidget(result_group)

        button_box = QtWidgets.QDialogButtonBox()
        self.compile_btn = button_box.addButton("编译波形", QtWidgets.QDialogButtonBox.ActionRole)
        self.rename_btn = button_box.addButton("重命名...", QtWidgets.QDialogButtonBox.ActionRole)
        self.update_btn = button_box.addButton("更新当前波形", QtWidgets.QDialogButtonBox.ActionRole)
        self.save_btn = button_box.addButton("另存为新波形...", QtWidgets.QDialogButtonBox.ActionRole)
        self.apply_btn = button_box.addButton("应用并更新到设备", QtWidgets.QDialogButtonBox.AcceptRole); self.apply_btn.setEnabled(False)
        button_box.addButton(QtWidgets.QDialogButtonBox.Cancel)
        main_layout.addWidget(button_box)
        
        if not self.current_waveform_info:
            self.update_btn.setEnabled(False)
            self.update_btn.setToolTip("只有在编辑一个已存在的波形时才能更新。")
            self.rename_btn.setEnabled(False)
            self.rename_btn.setToolTip("只有在编辑一个已存在的波形时才能重命名。")

        self.compile_btn.clicked.connect(self.compile_waveform)
        self.rename_btn.clicked.connect(self.rename_current_waveform)
        self.update_btn.clicked.connect(self.update_current_waveform)
        self.save_btn.clicked.connect(self.save_as_new_waveform)
        button_box.accepted.connect(self.apply_and_close)
        button_box.rejected.connect(self.reject)

    # (替换旧的 rename_current_waveform 函数)
    def rename_current_waveform(self):
        if not self.current_waveform_info:
            return

        # 步骤 0: 确保波形已编译
        if not hasattr(self, 'generated_data') or self.generated_data is None:
            if self.compile_waveform() is None:
                QtWidgets.QMessageBox.warning(self, "需要编译", "请先成功编译波形以确保数据同步，然后再重命名。")
                return

        old_display_name = self.current_waveform_info['name']
        old_c_variable_name = self.current_waveform_info['var_name']

        # 1. 获取用户输入的新显示名称
        new_display_name, ok = QtWidgets.QInputDialog.getText(self, "重构式重命名", 
            f"将同时重命名显示名称和C变量名。\n请输入 '{old_display_name}' 的新名称:", text=old_display_name)
        if not ok or not new_display_name.strip() or new_display_name.strip() == old_display_name:
            return
        new_display_name = new_display_name.strip()

        # 2. 生成新的 C 变量名
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '', new_display_name.replace(' ', '_'))
        new_c_variable_name = f"lut_{clean_name}_{len(self.generated_data)}bytes"

        profile_root = self.profile.get('__root_path__')
        lut_source_filename = self.profile.get('lut_source_file')
        json_path = self._find_profile_json(profile_root)

        if not all([profile_root, lut_source_filename, json_path]):
            QtWidgets.QMessageBox.critical(self, "配置错误", "Profile缺少'__root_path__', 'lut_source_file'或.json文件配置。")
            return
            
        # 3. 在修改文件前，检查JSON
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                profile_data_for_check = json.load(f)
            current_luts_check = profile_data_for_check.get("luts", {})
            # 检查新名称是否冲突
            if new_display_name in current_luts_check:
                QtWidgets.QMessageBox.warning(self, "命名冲突", f"显示名称 '{new_display_name}' 已存在，请使用其他名称。")
                return
            # 获取旧条目的信息，特别是 mode
            old_lut_info = current_luts_check.get(old_display_name)
            if not isinstance(old_lut_info, dict):
                 QtWidgets.QMessageBox.critical(self, "JSON格式错误", f"波形 '{old_display_name}' 在JSON中的格式不正确，无法获取模式信息。")
                 return
            old_mode = old_lut_info.get("mode")
            if not old_mode:
                 QtWidgets.QMessageBox.critical(self, "JSON格式错误", f"波形 '{old_display_name}' 在JSON中缺少 'mode' 标签。")
                 return
                 
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "文件读取失败", f"无法读取JSON文件进行检查: {e}")
            return
            
        # 4. 修改 C 源文件 (逻辑不变)
        lut_source_path = os.path.join(profile_root, lut_source_filename)
        try:
            # ... (省略读取、正则替换、写回 C 文件的代码，和您原来的一样) ...
            with open(lut_source_path, 'r', encoding='utf-8') as f:
                 source_code = f.read()
            pattern = re.compile(
                 r"(const\s+(?:unsigned\s+char|uint8_t)\s+)" + re.escape(old_c_variable_name) + r"(\s*\[[^\]]*\]\s*=\s*\{)"
            )
            if not pattern.search(source_code):
                 raise FileNotFoundError(f"在C源文件 '{lut_source_filename}' 中未找到变量 '{old_c_variable_name}' 的定义。")
            updated_source_code = pattern.sub(r"\1" + new_c_variable_name + r"\2", source_code, count=1)
            with open(lut_source_path, 'w', encoding='utf-8') as f:
                 f.write(updated_source_code)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "C文件更新失败", f"更新C源文件时发生错误:\n{e}")
            return

        # 5. 修改 JSON 配置文件 (写入新格式)
        try:
            with open(json_path, 'r+', encoding='utf-8') as f:
                profile_data = json.load(f)
                current_luts = profile_data.get("luts", {})
                
                # --- [ 修改此部分代码 ] ---
                # 删除旧条目
                current_luts.pop(old_display_name, None) 
                
                # 添加新条目 (使用新结构，保留旧模式)
                current_luts[new_display_name] = {
                    "variable": new_c_variable_name,
                    "mode": old_mode # 保留从旧条目读取的模式
                }
                # --- [ 修改结束 ] ---
                
                profile_data['luts'] = current_luts
                
                f.seek(0)
                f.truncate()
                json.dump(profile_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "JSON更新失败", f"更新JSON配置文件时发生错误:\n{e}")
            # 注意：回滚C文件更改
            return

        # 6. 更新UI和内部状态 (逻辑不变)
        self.log_to_parent(f"波形 '{old_display_name}' 已重构为 '{new_display_name}'。")
        QtWidgets.QMessageBox.information(self, "成功", "波形已成功重命名！")
        
        self.current_waveform_info['name'] = new_display_name
        self.current_waveform_info['var_name'] = new_c_variable_name
        self.final_waveform_name = new_display_name
        self.setWindowTitle(f"参数化波形编辑器 - 正在编辑: {new_display_name}")
        self.profile['luts'] = profile_data['luts'] # 更新内存中的profile


    # ... (其他函数保持不变) ...
    def populate_ui_from_data(self, lut_data: bytes):
        try:
            self.handler.populate(lut_data)
            self.log_to_parent("UI已根据传入的LUT数据成功填充。")
        except Exception as e:
            error_message = f"反向解析LUT并填充UI时发生错误: {e}"
            QtWidgets.QMessageBox.critical(self, "解析失败", error_message)
            self.log_to_parent(error_message)

    def compile_waveform(self):
        try:
            self.generated_data = self.handler.compile()
            c_array_name = self.current_waveform_info['var_name'] if self.current_waveform_info else "lut_temp_preview"
            formatted_text = self.handler.format_to_c_array(self.generated_data, var_name=c_array_name)
            self.result_text.setText(formatted_text)
            self.apply_btn.setEnabled(True)
            self.log_to_parent("波形已根据当前参数成功编译。")
            return self.generated_data
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "编译失败", f"编译波形时发生错误: {e}")
            self.apply_btn.setEnabled(False)
            self.generated_data = None
            return None

    def apply_and_close(self):
        if not hasattr(self, 'generated_data') or self.generated_data is None:
            if self.compile_waveform() is None: return
        self.lut_data_ready.emit(self.generated_data)
        self.accept()

    def update_current_waveform(self):
        if self.compile_waveform() is None:
            QtWidgets.QMessageBox.warning(self, "操作中止", "请先确保波形可以成功编译。")
            return
        reply = QtWidgets.QMessageBox.question(self, "确认更新", 
            f"您确定要用当前参数覆盖原始的 '{self.current_waveform_info['name']}' 波形吗？\n此操作不可撤销。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return
        profile_root = self.profile.get('__root_path__')
        lut_source_filename = self.profile.get('lut_source_file')
        c_array_variable_name = self.current_waveform_info['var_name']
        lut_source_path = os.path.join(profile_root, lut_source_filename)
        new_c_array_code = self.handler.format_to_c_array(self.generated_data, var_name=c_array_variable_name)
        try:
            with open(lut_source_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
            pattern = re.compile(
                r"(const\s+(?:unsigned\s+char|uint8_t)\s+" + re.escape(c_array_variable_name) + r"\s*\[[^\]]*\]\s*=\s*\{.*?\};)",
                re.DOTALL)
            if not pattern.search(source_code):
                QtWidgets.QMessageBox.critical(self, "更新失败", f"在文件 '{lut_source_filename}' 中找不到变量名为 '{c_array_variable_name}' 的C数组定义。\n\n请检查变量名或数组定义格式是否正确。")
                return
            updated_source_code = pattern.sub(new_c_array_code, source_code, count=1)
            with open(lut_source_path, 'w', encoding='utf-8') as f:
                f.write(updated_source_code)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "文件操作失败", f"更新波形数据到 '{lut_source_path}' 时发生错误:\n{e}")
            return
        QtWidgets.QMessageBox.information(self, "成功", f"波形 '{self.current_waveform_info['name']}' 已成功更新！")
        self.log_to_parent(f"波形 '{self.current_waveform_info['name']}' 已被更新。")

    # (用这个带有 print 的版本替换旧的 save_as_new_waveform 函数)
    def save_as_new_waveform(self):
        print("DEBUG: Entered save_as_new_waveform") # 调试信息

        # 1. 检查是否已编译
        if not hasattr(self, 'generated_data') or self.generated_data is None:
            print("DEBUG: Waveform not compiled, trying to compile...") # 调试信息
            if self.compile_waveform() is None:
                print("DEBUG: Compilation failed.") # 调试信息
                QtWidgets.QMessageBox.information(self, "提示", "请先成功编译波形，然后再保存。")
                return
            print("DEBUG: Compilation successful.") # 调试信息

        # 2. 检查 Profile 配置
        profile_root = self.profile.get('__root_path__')
        lut_source_filename = self.profile.get('lut_source_file')
        json_path = self._find_profile_json(profile_root)
        print(f"DEBUG: profile_root={profile_root}, lut_source_filename={lut_source_filename}, json_path={json_path}") # 调试信息
        if not all([profile_root, lut_source_filename, json_path]):
            print("DEBUG: Profile configuration missing.") # 调试信息
            QtWidgets.QMessageBox.warning(self, "配置错误", "当前Profile缺少'__root_path__', 'lut_source_file'或.json文件配置，无法保存。")
            return

        # 3. 弹出新对话框获取名称和模式
        print("DEBUG: Opening SaveWaveformDialog...") # 调试信息
        save_dialog = SaveWaveformDialog(self)
        dialog_result = save_dialog.exec_()
        print(f"DEBUG: SaveWaveformDialog result: {dialog_result}") # 调试信息

        if dialog_result == QtWidgets.QDialog.Accepted:
            waveform_name, selected_mode = save_dialog.get_save_details()
            print(f"DEBUG: User entered name='{waveform_name}', mode='{selected_mode}'") # 调试信息
            if not waveform_name:
                print("DEBUG: Waveform name is empty.") # 调试信息
                QtWidgets.QMessageBox.warning(self, "输入无效", "波形显示名称不能为空。")
                return
        else:
            print("DEBUG: User cancelled SaveWaveformDialog.") # 调试信息
            return # 用户取消

        # 4. 检查 JSON 中显示名称是否冲突
        print("DEBUG: Checking for JSON name conflict...") # 调试信息
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                profile_data_for_check = json.load(f)
            if waveform_name in profile_data_for_check.get("luts", {}):
                print(f"DEBUG: Name conflict found for '{waveform_name}'.") # 调试信息
                QtWidgets.QMessageBox.warning(self, "命名冲突", f"显示名称 '{waveform_name}' 已存在，请使用其他名称。")
                return
            print("DEBUG: No name conflict.") # 调试信息
        except Exception as e:
            print(f"DEBUG: Error reading JSON for conflict check: {e}") # 调试信息
            QtWidgets.QMessageBox.critical(self, "文件读取失败", f"无法读取JSON文件进行检查: {e}")
            return

        # 5. 生成 C 变量名
        clean_name = re.sub(r'[^a-zA-Z0-9_]', '', waveform_name.replace(' ', '_'))
        c_array_variable_name = f"lut_{clean_name}_{len(self.generated_data)}bytes"
        print(f"DEBUG: Generated C variable name: {c_array_variable_name}") # 调试信息

        # 6. 将波形数据写入 C 文件
        lut_source_path = os.path.join(profile_root, lut_source_filename)
        print(f"DEBUG: Attempting to write C array to: {lut_source_path}") # 调试信息
        try:
            final_c_array_code = self.handler.format_to_c_array(self.generated_data, var_name=c_array_variable_name)
            with open(lut_source_path, 'a+', encoding='utf-8') as f:
                f.seek(0, os.SEEK_END)
                if f.tell() > 0:
                   f.seek(f.tell() - 1, os.SEEK_SET)
                   last_char = f.read(1)
                   if last_char != '\n':
                       f.write('\n')
                f.write("\n" + final_c_array_code + "\n")
            print("DEBUG: Successfully wrote to C file.") # 调试信息
        except Exception as e:
            print(f"DEBUG: Error writing to C file: {e}") # 调试信息
            QtWidgets.QMessageBox.critical(self, "文件写入失败", f"无法将波形数据写入到 '{lut_source_path}':\n{e}")
            return

        # 7. 更新 JSON 文件 (写入新格式)
        print(f"DEBUG: Attempting to update JSON file: {json_path}") # 调试信息
        try:
            # 先读，再修改，最后写回 (更安全)
            with open(json_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)

            if "luts" not in profile_data:
                profile_data["luts"] = {}

            # --- [ 写入新结构 ] ---
            new_lut_entry = {
                "variable": c_array_variable_name,
                "mode": selected_mode
            }
            profile_data["luts"][waveform_name] = new_lut_entry
            print(f"DEBUG: New JSON 'luts' entry: {waveform_name} -> {new_lut_entry}") # 调试信息
            # --- [ 写入结束 ] ---

            with open(json_path, 'w', encoding='utf-8') as f: # 使用 'w' 覆盖写回
                json.dump(profile_data, f, indent=4, ensure_ascii=False)
            print("DEBUG: Successfully updated JSON file.") # 调试信息
        except Exception as e:
            print(f"DEBUG: Error updating JSON file: {e}") # 调试信息
            QtWidgets.QMessageBox.critical(self, "JSON更新失败", f"无法更新配置文件 '{json_path}':\n{e}")
            # 注意：此处最好能有回滚C文件更改的逻辑
            return

        # 8. 更新UI和状态
        print("DEBUG: Updating UI and internal state.") # 调试信息
        self.final_waveform_name = waveform_name
        self.profile['luts'] = profile_data['luts']
        
        QtWidgets.QMessageBox.information(self, "成功", f"波形 '{waveform_name}' 已成功保存到Profile '{self.ic_name}'!")
        self.log_to_parent(f"新波形 '{waveform_name}' (模式: {selected_mode}) 已保存。")
        print("DEBUG: save_as_new_waveform finished successfully.") # 调试信息

    def _find_profile_json(self, directory):
        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                return os.path.join(directory, filename)
        return None
        
    def log_to_parent(self, message):
        if self.parent() and hasattr(self.parent(), 'log_to_textarea'):
            self.parent().log_to_textarea(f"[Editor] {message}")
