"""
文件解析器：将各种格式的文件转换为纯文本，供 LLM 理解。

支持格式：
- .txt / .md / .py / .log / .cfg / .ini / .yaml / .yml / .sh — 纯文本
- .json — JSON 格式化
- .csv — 表格文本
- .xlsx / .xls — Excel 表格（openpyxl）
- .pdf — PDF 文档（PyPDF2）
- .docx — Word 文档（python-docx）
- .png / .jpg / .jpeg / .gif / .webp / .bmp — 图片 OCR
"""
import csv
import io
import json
import logging
import os
from datetime import datetime

from django.conf import settings

logger = logging.getLogger(__name__)

# 允许上传的文件扩展名
ALLOWED_EXTENSIONS = {
    '.txt', '.md', '.py', '.log', '.cfg', '.ini', '.yaml', '.yml', '.sh',
    '.json', '.csv', '.xlsx', '.xls', '.pdf', '.docx',
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp',
}

# 最大文件大小（字节）
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

# 解析后文本最大长度（避免超出 LLM 上下文窗口）
MAX_PARSED_LENGTH = 50000

# 图片最大尺寸（像素），超过则等比缩放
MAX_IMAGE_DIMENSION = 4096

# 纯文本扩展名集合
TEXT_EXTENSIONS = {'.txt', '.md', '.py', '.log', '.cfg', '.ini', '.yaml', '.yml', '.sh'}

# Excel 扩展名
EXCEL_EXTENSIONS = {'.xlsx', '.xls'}

# 图片扩展名
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}


def _truncate(text, max_len=MAX_PARSED_LENGTH):
    """截断过长的文本，尾附加提示。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + '\n\n... (文件过大，内容已截断)'


def _parse_text(raw_bytes, filename):
    """解析纯文本文件。"""
    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        try:
            return raw_bytes.decode('gbk')
        except UnicodeDecodeError:
            return raw_bytes.decode('latin-1')


def _parse_json(raw_bytes, filename):
    """解析 JSON 文件，格式化输出。"""
    text = _parse_text(raw_bytes, filename)
    try:
        data = json.loads(text)
        formatted = json.dumps(data, ensure_ascii=False, indent=2)
        return formatted
    except json.JSONDecodeError as e:
        raise ValueError(f'JSON 解析失败: {e}')


def _parse_csv_text(raw_bytes, filename):
    """解析 CSV 文件为 Markdown 表格格式。"""
    text = raw_bytes.decode('utf-8')
    # 检测分隔符
    dialect = csv.Sniffer().sniff(text[:2048])
    reader = csv.reader(io.StringIO(text), dialect)

    rows = []
    for row in reader:
        rows.append(row)
        if len(rows) > 500:
            rows.append(['... (超过500行，已截断)'])
            break

    if not rows:
        return '(空 CSV 文件)'

    # 转为 Markdown 表格
    lines = []
    # 表头
    header = rows[0]
    lines.append('| ' + ' | '.join(str(c) for c in header) + ' |')
    lines.append('| ' + ' | '.join('---' for _ in header) + ' |')
    # 数据行
    for row in rows[1:]:
        lines.append('| ' + ' | '.join(str(c) for c in row) + ' |')

    return '\n'.join(lines)


def _parse_excel(raw_bytes, filename):
    """解析 Excel 文件为 Markdown 格式文本。"""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    parts = []

    for sheet_name in wb.sheetnames[:5]:  # 最多解析 5 个 sheet
        ws = wb[sheet_name]
        parts.append(f'## Sheet: {sheet_name}')

        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(row)
            if len(rows) > 1000:
                rows.append(('... (超过1000行，已截断)',))
                break

        if rows:
            # Markdown 表格
            header = rows[0]
            col_count = len(header)
            parts.append('| ' + ' | '.join(str(c) if c is not None else '' for c in header) + ' |')
            parts.append('| ' + ' | '.join('---' for _ in range(col_count)) + ' |')
            for row in rows[1:]:
                parts.append('| ' + ' | '.join(
                    str(c) if c is not None else '' for c in row
                ) + ' |')

    wb.close()
    return '\n\n'.join(parts)


def _parse_pdf(raw_bytes, filename):
    """解析 PDF 文件，提取所有页面文本。"""
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        raise ImportError(
            '未安装 PyPDF2，无法解析 PDF 文件。'
            '请在终端运行: pip install PyPDF2'
        )

    pdf_file = io.BytesIO(raw_bytes)
    reader = PdfReader(pdf_file)
    pages_text = []
    total_pages = len(reader.pages)

    for i, page in enumerate(reader.pages):
        if i >= 50:  # 最多读取 50 页
            pages_text.append(f'\n... (PDF 共 {total_pages} 页，仅展示前 50 页)')
            break
        text = page.extract_text()
        if text:
            pages_text.append(f'--- 第 {i + 1} 页 ---\n{text.strip()}')

    if not pages_text:
        return '(PDF 文件中未检测到可提取的文本内容，可能是扫描件或图片型 PDF)'

    return '\n\n'.join(pages_text)


def _parse_docx(raw_bytes, filename):
    """解析 Word 文档，提取段落文本。"""
    try:
        from docx import Document
    except ImportError:
        raise ImportError(
            '未安装 python-docx，无法解析 Word 文档。'
            '请在终端运行: pip install python-docx'
        )

    doc = Document(io.BytesIO(raw_bytes))
    paragraphs = []

    # 提取段落
    for para in doc.paragraphs:
        if para.text.strip():
            # 检测标题样式
            if para.style.name.startswith('Heading'):
                level = para.style.name.split()[-1]
                try:
                    level_num = int(level)
                    prefix = '#' * min(level_num, 6)
                except ValueError:
                    prefix = '##'
                paragraphs.append(f'{prefix} {para.text}')
            else:
                paragraphs.append(para.text)

    # 提取表格
    for i, table in enumerate(doc.tables):
        paragraphs.append(f'\n**表格 {i + 1}:**')
        for row in table.rows[:50]:  # 每个表格最多 50 行
            cells = [cell.text for cell in row.cells]
            paragraphs.append(' | '.join(cells))

    if not paragraphs:
        return '(Word 文档中未检测到文本内容)'

    return '\n\n'.join(paragraphs)


def _parse_image(raw_bytes, filename):
    """
    解析图片：使用 OCR 提取文字内容。

    优先使用腾讯云 OCR，降级到 Tesseract。
    """
    from PIL import Image

    # 检查图片尺寸，过大则缩放
    img = Image.open(io.BytesIO(raw_bytes))
    width, height = img.size
    fmt = img.format or '未知'
    mode = img.mode

    resized = False
    if max(width, height) > MAX_IMAGE_DIMENSION:
        ratio = MAX_IMAGE_DIMENSION / max(width, height)
        new_size = (int(width * ratio), int(height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
        resized = True

    # 转为 JPEG 字节（腾讯云 OCR 对 JPEG 支持最好）
    buf = io.BytesIO()
    img_format = img.format or 'PNG'
    if img_format.upper() not in ('JPEG', 'PNG'):
        img = img.convert('RGB')
    img.save(buf, format='JPEG', quality=85)
    image_bytes = buf.getvalue()

    # 尝试腾讯云 OCR
    ocr_text = ''
    try:
        ocr_text = _try_tencent_ocr(image_bytes)
    except Exception as e:
        logger.warning('腾讯云 OCR 失败，尝试 Tesseract: %s', e)

    # 降级到 Tesseract
    if not ocr_text:
        try:
            ocr_text = _try_tesseract_ocr(image_bytes)
        except Exception as e:
            logger.warning('Tesseract OCR 也失败: %s', e)

    lines = [
        f'图片文件（已通过 OCR 提取文字内容）',
        f'格式: {fmt}',
        f'尺寸: {width} x {height} 像素' + (' (已缩放)' if resized else ''),
        f'色彩模式: {mode}',
    ]
    if ocr_text:
        lines.append(f'\n识别文字内容:\n{ocr_text}')
    else:
        lines.append('\n(未能从图片中识别到文字内容)')

    return '\n'.join(lines)


def _try_tencent_ocr(image_bytes):
    """调用腾讯云 OCR 提取图片文字。"""
    from base_utils.image_base import ImageBase
    from apis.ocr.views import _extract_detected_text_from_tencent_json

    # 读取密钥配置
    secret_id = getattr(settings, 'TENCENT_OCR_SECRET_ID', None)
    secret_key = getattr(settings, 'TENCENT_OCR_SECRET_KEY', None)

    img_base = ImageBase()
    if secret_id and secret_key:
        img_base.set_tencent_cloud_ocr_credentials(secret_id, secret_key)

    result = img_base.image_text_orc(image_bytes)
    if result and isinstance(result, dict):
        text = _extract_detected_text_from_tencent_json(result)
        return text.strip() if text else ''
    return ''


def _try_tesseract_ocr(image_bytes):
    """使用 Tesseract OCR 进行本地文字识别。"""
    import pytesseract
    from PIL import Image

    tesseract_cmd = getattr(settings, 'TESSERACT_CMD', None)
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img = Image.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img, lang='chi_sim+eng')
    return text.strip() if text else ''


def parse_file(raw_bytes, filename):
    """
    解析上传文件，返回文本内容。

    参数:
        raw_bytes: bytes — 文件的原始二进制数据
        filename: str — 原始文件名（用于判断扩展名）

    返回:
        dict — {
            "text": "解析后的文本内容",
            "filename": "原始文件名",
            "file_type": "文件类型标识",
            "size": 原始字节数,
            "parse_time": "解析时间 ISO 格式",
        }

    异常:
        ValueError — 不支持的文件类型或文件过大
        ImportError — 缺少解析该格式所需的库
    """
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f'不支持的文件类型（{ext}）。'
            f'支持的格式: {", ".join(sorted(ALLOWED_EXTENSIONS))}'
        )

    size = len(raw_bytes)
    if size > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise ValueError(f'文件过大（{size / 1024 / 1024:.1f}MB），最大允许 {max_mb:.0f}MB')

    logger.info('解析文件: %s (%s, %.1f KB)', filename, ext, size / 1024)

    # 按扩展名分发解析器
    if ext in TEXT_EXTENSIONS:
        text = _parse_text(raw_bytes, filename)
        file_type = 'Text'
    elif ext == '.json':
        text = _parse_json(raw_bytes, filename)
        file_type = 'JSON'
    elif ext == '.csv':
        text = _parse_csv_text(raw_bytes, filename)
        file_type = 'CSV'
    elif ext in EXCEL_EXTENSIONS:
        text = _parse_excel(raw_bytes, filename)
        file_type = 'Excel'
    elif ext == '.pdf':
        text = _parse_pdf(raw_bytes, filename)
        file_type = 'PDF'
    elif ext == '.docx':
        text = _parse_docx(raw_bytes, filename)
        file_type = 'Word'
    elif ext in IMAGE_EXTENSIONS:
        text = _parse_image(raw_bytes, filename)
        file_type = 'Image'
    else:
        # 兜底：尝试当纯文本处理
        text = _parse_text(raw_bytes, filename)
        file_type = 'Unknown'

    text = _truncate(text)
    logger.info(
        '文件解析完成: %s, 类型=%s, 原始=%d bytes, 解析后=%d chars',
        filename, file_type, size, len(text),
    )

    return {
        'text': text,
        'filename': filename,
        'file_type': file_type,
        'size': size,
        'parse_time': datetime.now().isoformat(),
    }
