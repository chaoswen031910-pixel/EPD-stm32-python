import numpy as np
from PIL import Image, ImageOps # [核心修改] 导入ImageOps
from PyQt5 import QtGui

class ImageProcessor:
    """一个用于处理图像以适应电子纸显示的工具类"""

    DITHER_KERNELS = {
        "Floyd-Steinberg": (
            np.array([
                [0., 0., 7.],
                [3., 5., 1.],
            ], dtype=np.float32) / 16.0,
            1 
        ),
        "Burkes": (
            [
                np.array([0, 0, 8, 4], dtype=np.float32) / 32.0,
                np.array([2, 4, 8, 4, 2], dtype=np.float32) / 32.0,
            ],
            2
        ),
        "Stucki": (
            [
                np.array([0, 0, 8, 4], dtype=np.float32) / 42.0,
                np.array([2, 4, 8, 4, 2], dtype=np.float32) / 42.0,
                np.array([1, 2, 4, 2, 1], dtype=np.float32) / 42.0,
            ],
            2
        ),
        "Atkinson": (
            [
                np.array([0, 0, 1, 1], dtype=np.float32) / 8.0,
                np.array([1, 1, 1, 0], dtype=np.float32) / 8.0,
                np.array([0, 1, 0, 0], dtype=np.float32) / 8.0,
            ],
            2
        ),
    }

    @staticmethod
    def pil_to_qpixmap(pil_img):
        """将Pillow Image对象转换为QPixmap对象"""
        if pil_img.mode == "1":
            img_data = pil_img.convert("L").tobytes("raw", "L")
            q_img = QtGui.QImage(img_data, pil_img.width, pil_img.height, pil_img.width, QtGui.QImage.Format_Grayscale8)
        elif pil_img.mode == "L":
            img_data = pil_img.tobytes("raw", "L")
            q_img = QtGui.QImage(img_data, pil_img.width, pil_img.height, pil_img.width, QtGui.QImage.Format_Grayscale8)
        else: # RGB
            img_data = pil_img.tobytes("raw", "RGB")
            q_img = QtGui.QImage(img_data, pil_img.width, pil_img.height, pil_img.width * 3, QtGui.QImage.Format_RGB888)
        return QtGui.QPixmap.fromImage(q_img)
    
    @staticmethod
    def format_bytes_as_c_array(data: bytes, var_name: str = "gImage_Data") -> str:
        """将bytes数据格式化为C语言的unsigned char数组字符串。"""
        if not data:
            return f"const unsigned char {var_name}[] = {{}};"
        lines = [f"// Image Data ({len(data)} bytes)"]
        lines.append(f"const unsigned char {var_name}[{len(data)}] = {{")
        line = "    "
        for i, byte in enumerate(data):
            if i > 0 and i % 16 == 0:
                lines.append(line.rstrip(','))
                line = "    "
            line += f"0x{byte:02X}, "
        if line.strip() != "":
            lines.append(line.rstrip(', '))
        lines.append("};")
        return "\n".join(lines)

    @staticmethod
    def _apply_dithering(pil_image, palette, kernel_name):
        """
        通用的抖动算法应用函数。
        """
        kernel, offset = ImageProcessor.DITHER_KERNELS[kernel_name]
        img_array = np.array(pil_image, dtype=np.float32)
        height, width = img_array.shape

        for y in range(height):
            for x in range(width):
                old_pixel = img_array[y, x]
                new_pixel = palette[np.argmin(np.abs(palette.astype(np.float32) - old_pixel))]
                img_array[y, x] = new_pixel
                quant_error = old_pixel - new_pixel
                
                if isinstance(kernel, list):
                    for row_idx, row in enumerate(kernel):
                        y_offset = y + row_idx + 1
                        if y_offset < height:
                            for col_idx, weight in enumerate(row):
                                x_offset = x + col_idx - offset
                                if 0 <= x_offset < width:
                                    img_array[y_offset, x_offset] += quant_error * weight
                else: 
                    for row_idx, row in enumerate(kernel):
                        y_offset = y + row_idx
                        if y_offset < height:
                            for col_idx, weight in enumerate(row):
                                x_offset = x + col_idx - offset
                                if 0 <= x_offset < width:
                                    img_array[y_offset, x_offset] += quant_error * weight

        dithered_array = np.clip(img_array, 0, 255).astype(np.uint8)
        return Image.fromarray(dithered_array, 'L')

    @staticmethod
    def pack_4gray_data_for_ssd(pil_image):
        if pil_image.mode != 'L':
            raise ValueError("输入图像必须为8-bit灰度图 (mode 'L')")
        pixels = np.array(pil_image, dtype=np.uint8).flatten()
        two_bit_values = np.piecewise(pixels,
                                        [pixels <= 64,
                                         (pixels > 64) & (pixels <= 128),
                                         (pixels > 128) & (pixels <= 192)],
                                        [0, 1, 2, 3])
        inversion_map = {0: 3, 1: 2, 2: 1, 3: 0}
        inverted_two_bit_values = np.vectorize(inversion_map.get)(two_bit_values)
        map_0x24 = {0: 1, 1: 0, 2: 1, 3: 0}
        map_0x26 = {0: 1, 1: 1, 2: 0, 3: 0}
        bits_for_buffer1 = np.vectorize(map_0x24.get)(inverted_two_bit_values)
        bits_for_buffer2 = np.vectorize(map_0x26.get)(inverted_two_bit_values)
        buffer1 = np.packbits(bits_for_buffer1)
        buffer2 = np.packbits(bits_for_buffer2)
        return bytes(buffer1), bytes(buffer2)

    # --- [核心修改] 用这个新版本替换旧的 process_image 函数 ---
    @staticmethod
    def process_image(image_path, resolution, mode, **kwargs):
        """
        处理图像的核心函数。
        """
        native_width, native_height = resolution
        rotation = kwargs.get('rotation', 0)
        invert_color = kwargs.get('invert_color', False)
        mirror_horizontal = kwargs.get('mirror_horizontal', False)
        mirror_vertical = kwargs.get('mirror_vertical', False)

        original_img = Image.open(image_path)
        
        # --- 增加的逻辑：判断是否跳过颜色量化 ---
        bypass_quantization = False
        if mode == '4gray':
            try:
                # 检查图片是否已经是简单的灰度图(L模式)或索引图(P模式)
                if original_img.mode in ('L', 'P'):
                    # 获取图片中的颜色数量
                    unique_colors = original_img.getcolors(maxcolors=5)
                    # 如果颜色少于等于4种，就认为它已经是我们想要的格式
                    if unique_colors and len(unique_colors) <= 4:
                        bypass_quantization = True
            except Exception:
                pass # 如果检查出错，则走标准流程以确保稳定
        # --- 判断结束 ---

        # 1. 旋转
        if rotation == 90: rotated_img = original_img.transpose(Image.Transpose.ROTATE_270)
        elif rotation == 180: rotated_img = original_img.transpose(Image.Transpose.ROTATE_180)
        elif rotation == 270: rotated_img = original_img.transpose(Image.Transpose.ROTATE_90)
        else: rotated_img = original_img
        
        # 2. 镜像和翻转
        transformed_img = rotated_img
        if mirror_horizontal:
            transformed_img = ImageOps.mirror(transformed_img)
        if mirror_vertical:
            transformed_img = ImageOps.flip(transformed_img)

        # 3. 缩放与画布粘贴
        img_aspect = transformed_img.width / transformed_img.height
        screen_aspect = native_width / native_height
        if img_aspect > screen_aspect:
            new_w = native_width
            new_h = int(new_w / img_aspect)
        else:
            new_h = native_height
            new_w = int(new_h * img_aspect)

        resized_img = transformed_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        canvas = Image.new('L', (native_width, native_height), 255)
        paste_x = (native_width - new_w) // 2
        paste_y = (native_height - new_h) // 2
        canvas.paste(resized_img.convert('L'), (paste_x, paste_y))
        grayscale_img = canvas

        # 4. 颜色反转
        if invert_color:
            grayscale_img = ImageOps.invert(grayscale_img)

        # 5. 模式处理 (抖动、阈值、量化)
        if mode == 'floyd-steinberg':
            palette_bw = np.array([0, 255], dtype=np.uint8)
            dithered_grayscale_img = ImageProcessor._apply_dithering(grayscale_img, palette_bw, "Floyd-Steinberg")
            return dithered_grayscale_img.convert('1')
        
        elif mode == 'threshold':
            threshold_value = kwargs.get('threshold_value', 128)
            return grayscale_img.point(lambda p: 255 if p > threshold_value else 0, '1')

        elif mode == '4gray':
            # --- 增加的逻辑：如果检测到是原始4灰阶图，则直接返回，跳过后续量化 ---
            if bypass_quantization:
                return grayscale_img # 此时 grayscale_img 已经过了旋转、缩放、反色等处理
            # --- 判断结束 ---
            
            dither_method = kwargs.get('dither_method', None)
            palette_4gray = np.array([0, 85, 170, 255], dtype=np.uint8)
            
            if dither_method and dither_method in ImageProcessor.DITHER_KERNELS:
                return ImageProcessor._apply_dithering(grayscale_img, palette_4gray, dither_method)
            else: # 无抖动
                img_array = np.array(grayscale_img, dtype=np.uint8)
                quantized_array = np.piecewise(img_array, 
                                               [img_array <= 64, 
                                                (img_array > 64) & (img_array <= 128), 
                                                (img_array > 128) & (img_array <= 192)],
                                               [0, 85, 170, 255])
                return Image.fromarray(quantized_array.astype(np.uint8), 'L')
            
        else:
            raise ValueError(f"未知的图像处理模式: {mode}")