# 文件: utils.py

import datetime
import os
import sys
import configparser

# --- 辅助函数：获取 App 基础路径 (.exe 所在目录) ---
def get_app_base_path():
    """获取 App 的基础路径 (无论是 .py 还是 .exe)"""
    if getattr(sys, 'frozen', False):
        # 打包后的 .exe 模式
        return os.path.dirname(sys.executable)
    else:
        # 开发模式 (.py)
        # 我们假设 utils.py 在项目根目录，和 main.py 一起
        return os.path.abspath(".")

# --- 配置文件名和路径 ---
CONFIG_FILE = 'settings.ini'
CONFIG_FILE_PATH = os.path.join(get_app_base_path(), CONFIG_FILE)


# --- 读取配置 (无需修改) ---
def get_custom_profiles_path():
    """
    从 settings.ini 读取自定义的 profiles 路径。
    如果未设置或文件不存在，返回 None。
    """
    if not os.path.exists(CONFIG_FILE_PATH):
        return None
    
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE_PATH, encoding='utf-8')
        path = config.get('Settings', 'ProfilesPath', fallback=None)
        
        if path and os.path.isdir(path):
            return path
        
    except Exception as e:
        print(f"Error reading config file: {e}")
        
    return None

# --- 保存配置 (无需修改) ---
def save_custom_profiles_path(path):
    """将自定义路径保存到 settings.ini"""
    config = configparser.ConfigParser()
    try:
        config.read(CONFIG_FILE_PATH, encoding='utf-8')
    except Exception:
        pass 

    if 'Settings' not in config:
        config['Settings'] = {}
    
    config['Settings']['ProfilesPath'] = path
    
    try:
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            config.write(f)
        return True
    except Exception as e:
        print(f"Error writing config file: {e}")
        return False

# --- [ 关键修改 ] ---
# --- 更新：get_user_data_path ---
def get_user_data_path(relative_path):
    """
    获取用户数据文件的路径。
    1. (开发模式 .py): 总是使用 .py 旁边的路径。
    2. (打包模式 .exe): 优先检查自定义路径 (settings.ini)，否则使用 .exe 旁边的路径。
    """
    is_bundled = getattr(sys, 'frozen', False)

    if not is_bundled:
        # --- 情况1：开发模式 (.py) ---
        # 总是返回 .py 文件旁边的路径 (例如: E:\projects\stm32Py\profiles)
        # 此时完全忽略 settings.ini
        return os.path.join(get_app_base_path(), relative_path)
    
    else:
        # --- 情况2：打包模式 (.exe) ---
        # 遵循用户路径
        if relative_path.lower() == 'profiles':
            custom_path = get_custom_profiles_path()
            if custom_path:
                # 如果设置了自定义路径，它 *就是* profiles 目录
                return custom_path
            
        # 对于 'log.txt' 或 默认的 'profiles'，使用 .exe 旁边的基础路径
        return os.path.join(get_app_base_path(), relative_path)


# --- 捆绑资源路径 (无需修改) ---
def get_bundle_path(relative_path):
    """
    获取 *捆绑* 在 .exe 内部的资源路径.
    (在开发模式下，这返回的路径和 get_user_data_path 一样)
    """
    if getattr(sys, 'frozen', False):
        # 打包后的 .exe
        if hasattr(sys, '_MEIPASS'):
            # --onefile 模式
            base_path = sys._MEIPASS
        else:
            # --onedir 模式
            base_path = os.path.dirname(sys.executable)
            internal_dir = os.path.join(base_path, '_internal')
            if os.path.exists(internal_dir):
                base_path = internal_dir
    else:
        # 开发模式 .py
        base_path = os.path.abspath(".") 

    return os.path.join(base_path, relative_path)

# --- 日志 (无需修改) ---
LOG_FILE = "log.txt"

def log_message(message):
    """将带时间戳的消息写入日志文件"""
    
    # [ 逻辑更新 ]：
    # 在 .py 模式下，log.txt 会在项目根目录。
    # 在 .exe 模式下，log.txt 会在 .exe 旁边 (除非 profiles 被重定向，但日志不会)
    log_file_path = os.path.join(get_app_base_path(), LOG_FILE)
    
    timestamp = datetime.datetime.now().strftime("%Y-m-d %H:%M:%S.%f")[:-3]
    try:
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} - {message}\n")
    except Exception as e:
        print(f"Failed to write to log file: {e}")