from PyQt5 import QtWidgets, QtCore, QtGui

class UserGuideDialog(QtWidgets.QDialog):
    """
    一个专门用于显示快速入门指南的对话框。
    内容使用HTML格式，以获得更好的排版效果。
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("快速入门指南")
        self.setMinimumSize(800, 600)

        # 使用QTextBrowser可以支持富文本和超链接
        self.text_browser = QtWidgets.QTextBrowser()
        self.text_browser.setOpenExternalLinks(True) 

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.text_browser)

        self._set_guide_content()

    def _set_guide_content(self):
        """设置指南的HTML内容"""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body { 
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; 
                    line-height: 1.6; 
                    background-color: #ffffff;
                }
                h1 { 
                    color: #2c3e50; 
                    border-bottom: 2px solid #3498db; 
                    padding-bottom: 10px; 
                }
                h2 { 
                    color: #34495e; 
                    border-bottom: 1px solid #bdc3c7; 
                    padding-bottom: 5px; 
                }
                p { color: #555; }
                code { 
                    background-color: #ecf0f1; 
                    padding: 2px 5px; 
                    border-radius: 4px; 
                    font-family: "Courier New", Courier, monospace; 
                    color: #e74c3c;
                }
                strong { color: #c0392b; }
                .step { 
                    margin-bottom: 20px; 
                    padding: 15px; 
                    border-left: 5px solid #3498db; 
                    background-color: #f8f9f9; 
                    border-radius: 5px;
                }
                .note { 
                    margin-top: 15px; 
                    padding: 10px; 
                    border: 1px solid #f1c40f; 
                    background-color: #fef9e7; 
                    border-radius: 5px; 
                }
            </style>
        </head>
        <body>
            <h1>上位机快速入门指南</h1>
            <p>本指南将引导您完成点亮电子纸屏幕所需的核心步骤。</p>

            <h2>准备工作</h2>
            <ul>
                <li><strong>硬件连接</strong>：请确保驱动板已通过 USB 线连接到电脑。</li>
                <li><strong>驱动安装</strong>：请确保电脑已正确安装串口驱动 (如 CH340)，并能在设备管理器中看到 COM 端口。</li>
            </ul>

            <hr>

            <div class="step">
                <h2>第 1 步：连接设备</h2>
                <ol>
                    <li>在左上角 <strong>“端口选择”</strong> 区域，点击 <strong>“刷新”</strong> 按钮，软件将自动扫描并识别驱动板。</li>
                    <li>确认端口无误后，点击 <strong>“打开”</strong> 按钮。日志区提示 <code>[INFO] 已连接设备...</code> 表示连接成功。</li>
                </ol>
            </div>

            <div class="step">
                <h2>第 2 步：选择屏幕 Profile</h2>
                <ol>
                    <li>在顶部的 <strong>“IC Profile 选择”</strong> 下拉菜单中，根据您电子纸的 <strong>驱动 IC 型号和尺寸</strong> 选择对应的 Profile。</li>
                    <li><strong>这是最关键的一步！</strong> 软件将根据您的选择加载屏幕分辨率、初始化代码等所有配置。</li>
                </ol>
            </div>

            <div class="step">
                <h2>第 3 步：硬件复位与初始化</h2>
                <ol>
                    <li>在 <strong>“设备控制”</strong> 区域，首先点击 <strong>“硬件复位 (Reset)”</strong> 按钮。</li>
                    <li>接着，在 <strong>“初始化序列”</strong> 部分，点击右侧的 <strong>“执行”</strong> 按钮，完成屏幕上电初始化。</li>
                </ol>
            </div>

            <div class="step">
                <h2>第 4 步：更新LUT波形</h2>
                <ol>
                    <li>在 <strong>“设备控制”</strong> 区域的 <strong>“预设波形”</strong> 部分，从下拉框中选择一个波形（如 GC-16, DU-4 等）。</li>
                    <li>点击右侧的 <strong>“更新”</strong> 按钮，将该波形数据发送到设备的 RAM 中。<strong>此步骤对于获得最佳显示效果至关重要。</strong></li>
                </ol>
            </div>

            <div class="step">
                <h2>第 5 步：添加并预览图片</h2>
                <ol>
                    <li>在 <strong>“图像工作区”</strong> 点击 <strong>“添加图片”</strong> 按钮，选择您想要显示的图片。</li>
                    <li>在下方队列中<strong>单击</strong>图片，即可在右侧预览区看到处理后的效果。您可以在“图像参数”中调整旋转、抖动等选项。</li>
                </ol>
            </div>

            <div class="step">
                <h2>第 6 步：发送图片到屏幕</h2>
                <ol>
                    <li>确认预览效果满意后，点击右下角的 <strong>“开始发送”</strong> 按钮。</li>
                    <li>等待进度条走完，您的图片就会显示在电子纸屏幕上！</li>
                </ol>
            </div>

        </body>
        </html>
        """
        self.text_browser.setHtml(html_content)