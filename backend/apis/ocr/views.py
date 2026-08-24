"""
图片文字识别（服务端）

默认：上传图片 → base64_en(read_bytes) → 腾讯云通用高精度印刷体识别（image_base.image_text_orc），
按 TextDetections[].ItemPolygon（左上角 X、Y 及宽高；缺失时用 Polygon 外接矩形）将各行还原为近似版面后返回文本。

依赖：pip install tencentcloud-sdk-python（见 requirements.txt）

密钥：优先 Django settings / 环境变量 TENCENT_OCR_SECRET_ID、TENCENT_OCR_SECRET_KEY；
未配置时回退 base_utils.image_base.ImageBase 内默认值。

可选：query ?engine=tesseract 时使用本机 Tesseract（需安装 tesseract + pytesseract），lang 仅对该模式有效。
"""
import io
import json
import logging
import os
import shutil
import sys

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.users.decorators import require_valid_token

logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 12 * 1024 * 1024
ALLOWED_PREFIXES = ('image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp')


def _fail(msg, code=400, status=400):
    return JsonResponse({'code': code, 'message': msg, 'data': None}, status=status)


def _normalize_ocr_text(text):
    if not text:
        return ''
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln.rstrip() for ln in text.split('\n')]
    while lines and lines[-1] == '':
        lines.pop()
    return '\n'.join(lines)


def _bbox_from_text_detection(d):
    """
    从单条 TextDetection 取排版用矩形 (x, y, w, h)。
    优先 ItemPolygon（旋转纠正后左上角 + 宽高）；否则用 Polygon 四点外接矩形。
    """
    if not isinstance(d, dict):
        return None
    ip = d.get('ItemPolygon')
    if isinstance(ip, dict):
        x, y = ip.get('X'), ip.get('Y')
        if x is not None and y is not None:
            return int(x), int(y), int(ip.get('Width') or 0), int(ip.get('Height') or 0)
    poly = d.get('Polygon')
    if isinstance(poly, list) and len(poly) >= 2:
        xs, ys = [], []
        for p in poly:
            if not isinstance(p, dict):
                continue
            px, py = p.get('X'), p.get('Y')
            if px is not None and py is not None:
                xs.append(int(px))
                ys.append(int(py))
        if xs and ys:
            minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
            return minx, miny, maxx - minx, maxy - miny
    return None


def _estimated_text_width_px(text, unit_px):
    """按等宽近似估算文本占位宽度（像素），用于缺少 Width 时的横向间距。"""
    w = 0.0
    for ch in text:
        o = ord(ch)
        if o <= 0x20:
            continue
        w += unit_px * (1.9 if o > 0x2FF else 1.0)
    return max(w, unit_px * 2)


def _collect_tencent_detection_boxes(detections):
    """TextDetections → [{text, x, y, w, h}, ...]，保持接口顺序作为无坐标时的兜底。"""
    boxes = []
    if not isinstance(detections, list):
        return boxes
    for idx, d in enumerate(detections):
        if not isinstance(d, dict):
            continue
        raw = d.get('DetectedText')
        if raw is None or not str(raw).strip():
            continue
        text = str(raw).strip().replace('\r\n', ' ').replace('\n', ' ')
        bbox = _bbox_from_text_detection(d)
        if bbox is None:
            boxes.append({'text': text, 'x': 0, 'y': idx * 48, 'w': 0, 'h': 24})
        else:
            x, y, w, h = bbox
            boxes.append({'text': text, 'x': x, 'y': y, 'w': w, 'h': h or 20})
    return boxes


def _spatial_text_from_boxes(boxes):
    """
    按 Y 聚类为行、行内按 X 排序，用空格近似横向间隔（等宽文本域中阅读）。
    """
    if not boxes:
        return ''
    heights = [b['h'] for b in boxes if b.get('h', 0) > 1]
    median_h = sorted(heights)[len(heights) // 2] if heights else 22
    merge_y = max(median_h * 0.55, 12.0)
    unit_px = max(5.5, min(median_h * 0.42, 11.0))

    ordered = sorted(boxes, key=lambda b: (b['y'], b['x']))
    rows = []
    for b in ordered:
        yc = b['y'] + (b['h'] or median_h) * 0.5
        placed = False
        for row in rows:
            row_ycs = [x['y'] + (x['h'] or median_h) * 0.5 for x in row]
            ryc = sum(row_ycs) / len(row_ycs)
            if abs(yc - ryc) <= merge_y:
                row.append(b)
                placed = True
                break
        if not placed:
            rows.append([b])

    rows.sort(key=lambda row: sum(x['y'] for x in row) / len(row))
    out_lines = []
    for row in rows:
        row.sort(key=lambda b: b['x'])
        parts = []
        prev_right = None
        for b in row:
            t = b['text']
            if not t:
                continue
            x, w_box = b['x'], b.get('w') or 0
            if prev_right is None:
                parts.append(t)
            else:
                gap = x - prev_right
                if gap > unit_px * 0.35:
                    nsp = max(1, min(120, int(round(gap / unit_px))))
                    parts.append(' ' * nsp + t)
                else:
                    parts.append(' ' + t)
            est_w = w_box if w_box > 2 else _estimated_text_width_px(t, unit_px)
            prev_right = x + est_w
        line = ''.join(parts).rstrip()
        if line:
            out_lines.append(line)
    return '\n'.join(out_lines)


def _extract_detected_text_from_tencent_json(resp_json_str):
    """
    解析腾讯云 GeneralAccurateOCR 的 to_json_string()，
    按 ItemPolygon / Polygon 坐标排版后输出文本。
    """
    if not resp_json_str:
        return ''
    try:
        obj = json.loads(resp_json_str)
    except json.JSONDecodeError:
        logger.warning('tencent ocr response not json')
        return ''
    detections = obj.get('TextDetections')
    boxes = _collect_tencent_detection_boxes(detections)
    return _spatial_text_from_boxes(boxes)


def _resolve_tesseract_cmd():
    explicit = getattr(settings, 'TESSERACT_CMD', None)
    if explicit and os.path.isfile(explicit):
        return explicit
    w = shutil.which('tesseract')
    if w and os.path.isfile(w):
        return w
    candidates = [
        '/opt/homebrew/bin/tesseract',
        '/usr/local/bin/tesseract',
        '/usr/bin/tesseract',
    ]
    if sys.platform == 'win32':
        candidates.insert(
            0,
            os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'Tesseract-OCR', 'tesseract.exe'),
        )
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _configure_pytesseract(pytesseract):
    cmd = _resolve_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    return cmd


def _pad_image_for_ocr(img):
    from PIL import Image

    w, h = img.size
    side = max(8, min(w, h) // 100)
    bottom = max(side * 2, 20)
    nw, nh = w + 2 * side, h + side + bottom
    canvas = Image.new('RGB', (nw, nh), (255, 255, 255))
    canvas.paste(img, (side, side))
    return canvas


def _ocr_tesseract(raw, lang):
    import pytesseract
    from PIL import Image

    if not _configure_pytesseract(pytesseract):
        raise RuntimeError('tesseract_not_found')
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    img = _pad_image_for_ocr(img)
    tess_cfg = '--oem 3 --dpi 300'
    return pytesseract.image_to_string(img, lang=lang, config=tess_cfg)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def image_ocr(request):
    """
    multipart/form-data，字段名：image
    默认：腾讯云 OCR（与 base_utils 中 base64_en + image_text_orc 链路一致）
    ?engine=tesseract：本机 Tesseract；lang=chi_sim+eng|chi_sim|eng 仅对该模式有效
    """
    f = request.FILES.get('image')
    if not f:
        return _fail('请上传图片字段 image（multipart/form-data）')

    ct = (getattr(f, 'content_type', None) or '').lower()
    if not any(ct.startswith(p) for p in ALLOWED_PREFIXES):
        return _fail(f'不支持的图片类型: {ct or "unknown"}')

    raw = f.read()
    if len(raw) > MAX_IMAGE_BYTES:
        return _fail('图片过大，请压缩后重试（最大约 12MB）', 413, 413)

    lang = (request.GET.get('lang') or request.POST.get('lang') or 'chi_sim+eng').strip()
    if lang not in ('chi_sim+eng', 'chi_sim', 'eng'):
        lang = 'chi_sim+eng'

    engine = (request.GET.get('engine') or request.POST.get('engine') or 'tencent').strip().lower()

    if engine == 'tesseract':
        try:
            import pytesseract
        except ImportError:
            return _fail('服务端未安装 pytesseract，请检查 requirements.txt', 503, 503)
        try:
            text = _ocr_tesseract(raw, lang)
        except RuntimeError as e:
            if str(e) == 'tesseract_not_found':
                return _fail(
                    '未检测到 Tesseract 可执行文件，请安装或设置 TESSERACT_CMD',
                    503,
                    503,
                )
            logger.exception('tesseract ocr')
            return _fail('识别失败: ' + str(e), 500, 500)
        except Exception as e:
            logger.exception('tesseract ocr')
            return _fail('识别失败: ' + str(e), 500, 500)
        return JsonResponse({
            'code': 0,
            'message': 'ok',
            'data': {
                'text': _normalize_ocr_text(text),
                'lang': lang,
                'engine': 'tesseract',
            },
        })

    # 腾讯云：等同 image_text_orc(base64_en(read_file_by_rb(...), is_file=True))
    try:
        from base_utils.secrecy_base import base64_en
        from base_utils.image_base import ImageBase
    except ImportError as e:
        logger.warning('ocr import failed: %s', e)
        return _fail('服务端缺少 base_utils 或依赖', 503, 503)

    try:
        from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
    except ImportError:
        return _fail('请安装腾讯云 SDK：pip install tencentcloud-sdk-python', 503, 503)

    b64 = base64_en(raw, is_file=True)
    img_base = ImageBase(
        secret_id=getattr(settings, 'TENCENT_OCR_SECRET_ID', None),
        secret_key=getattr(settings, 'TENCENT_OCR_SECRET_KEY', None),
    )
    try:
        resp_json_str = img_base.image_text_orc(b64)
    except TencentCloudSDKException as e:
        logger.exception('tencent ocr api')
        return _fail('腾讯云识别失败: ' + str(e), 502, 502)
    except Exception as e:
        logger.exception('tencent ocr')
        return _fail('识别失败: ' + str(e), 500, 500)

    text = _extract_detected_text_from_tencent_json(resp_json_str)

    return JsonResponse({
        'code': 0,
        'message': 'ok',
        'data': {
            'text': _normalize_ocr_text(text),
            'engine': 'tencent',
        },
    })
