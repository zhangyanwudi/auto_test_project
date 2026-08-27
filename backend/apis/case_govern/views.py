import base64
import hashlib
import io
import json
import logging
import posixpath
import re
import zipfile
import xml.etree.ElementTree as ET
from urllib.parse import quote

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.case_govern.models import ZCaseGovernCase, ZCaseGovernCaseNode, ZCaseGovernModule
from apps.users.decorators import require_valid_token

logger = logging.getLogger('apis.case_govern')

NODE_TYPES = ('module', 'case', 'step', 'expect', 'precondition')
PRIORITY_MAP = {1: '高', 2: '中', 3: '低'}
# 导入 .emmx / .xmind 时按层级映射节点类型：0-根主题(模块)，其余层级统一映射为用例
IMPORT_DEPTH_TYPE = {0: 'module'}
# 导入 .emmx / .xmind 时用例归属模块（文件不含模块信息，归入「其它」）
IMPORT_DEFAULT_MODULE = '其它'


def _fmt_dt(dt):
    """转为北京时间（+8）的格式化字符串。"""
    if not dt:
        return None
    return timezone.localtime(dt).strftime('%Y-%m-%d %H:%M:%S')


def _serialize_case(c, node_count=None):
    return {
        'id': c.id,
        'case_name': c.case_name,
        'module': c.module or '',
        'priority': c.priority,
        'priority_label': PRIORITY_MAP.get(c.priority, ''),
        'status': c.status,
        'creator': c.creator or '',
        'description': c.description or '',
        'image': c.image or '',
        'has_image': bool(c.image),
        'node_count': node_count if node_count is not None else 0,
        'create_time': _fmt_dt(c.create_time),
        'update_time': _fmt_dt(c.update_time),
    }


def _parse_body(request):
    try:
        return json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return None


def _current_user_name(request):
    """创建人：优先取登录用户中文名，回退登录名。"""
    user = getattr(request, 'z_user', None)
    if not user:
        return ''
    return (getattr(user, 'user_cn_name', '') or getattr(user, 'user_name', '') or '').strip()


def _ensure_module(module):
    """模块非空且模块表不存在时自动沉淀，供下次下拉选择。"""
    if not module:
        return
    ZCaseGovernModule.objects.get_or_create(
        module_name=module, defaults={'status': 1, 'sort_order': 0}
    )


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def module_list(request):
    """列出启用的模块（供新建用例下拉选择）。"""
    qs = ZCaseGovernModule.objects.filter(status=1).order_by('sort_order', 'id')
    return JsonResponse({'code': 0, 'data': [m.module_name for m in qs]})


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def case_list(request):
    """用例列表（按 id 倒序），附带节点数统计。"""
    qs = ZCaseGovernCase.objects.annotate(node_count=Count('nodes')).order_by('-id')
    return JsonResponse({'code': 0, 'data': [_serialize_case(c, c.node_count) for c in qs]})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_create(request):
    """新增用例记录（创建人取自登录用户；同一模块下用例名称唯一）。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    case_name = (body.get('case_name') or '').strip()
    module = (body.get('module') or '').strip()
    if not case_name:
        return JsonResponse({'code': 400, 'message': '用例名称不能为空'}, status=400)
    if ZCaseGovernCase.objects.filter(case_name=case_name, module=module).exists():
        return JsonResponse({'code': 400, 'message': '同一模块下已存在同名用例'}, status=400)
    priority = int(body.get('priority') if body.get('priority') is not None else 2)
    if priority not in (1, 2, 3):
        return JsonResponse({'code': 400, 'message': '优先级须为 1/2/3'}, status=400)
    c = ZCaseGovernCase.objects.create(
        case_name=case_name,
        module=module,
        priority=priority,
        status=int(body.get('status') if body.get('status') is not None else 1),
        creator=_current_user_name(request),
        description=(body.get('description') or '').strip(),
        image=(body.get('image') or '').strip(),
    )
    _ensure_module(module)
    return JsonResponse({'code': 0, 'message': '创建成功', 'data': _serialize_case(c, 0)})


@csrf_exempt
@require_http_methods(['PUT'])
@require_valid_token
def case_update(request, pk):
    """编辑用例基本信息（创建人不随编辑变更；同一模块下用例名称唯一）。"""
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    try:
        c = ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)
    case_name = (body.get('case_name') or '').strip()
    if not case_name:
        return JsonResponse({'code': 400, 'message': '用例名称不能为空'}, status=400)
    module = (body.get('module') if 'module' in body else c.module)
    module = (module or '').strip()
    if ZCaseGovernCase.objects.exclude(pk=pk).filter(case_name=case_name, module=module).exists():
        return JsonResponse({'code': 400, 'message': '同一模块下已存在同名用例'}, status=400)
    c.case_name = case_name
    c.module = module
    if 'priority' in body:
        priority = int(body.get('priority') or 2)
        if priority not in (1, 2, 3):
            return JsonResponse({'code': 400, 'message': '优先级须为 1/2/3'}, status=400)
        c.priority = priority
    if 'status' in body:
        c.status = int(body.get('status') if body.get('status') is not None else 1)
    if 'description' in body:
        c.description = (body.get('description') or '').strip()
    if 'image' in body:
        c.image = (body.get('image') or '').strip()
    c.save()
    _ensure_module(module)
    return JsonResponse({'code': 0, 'message': '保存成功', 'data': _serialize_case(c)})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_delete(request, pk):
    """删除用例（级联删除思维导图节点）。"""
    try:
        c = ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)
    with transaction.atomic():
        c.nodes.all().delete()
        c.delete()
    return JsonResponse({'code': 0, 'message': '已删除'})


def _build_tree(rows):
    """按 parent_id 将扁平节点组装成树（正常只有一个根）。"""
    nodes = {r['id']: {**r, 'children': []} for r in rows}
    roots = []
    for r in rows:
        node = nodes[r['id']]
        pid = r['parent_id']
        if pid and pid in nodes:
            nodes[pid]['children'].append(node)
        else:
            roots.append(node)
    return roots


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def case_mind(request, pk):
    """获取用例的思维导图树；无节点时返回默认根节点。"""
    try:
        c = ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)
    rows = list(
        ZCaseGovernCaseNode.objects.filter(case_id=pk)
        .order_by('sort_order', 'id')
        .values('id', 'parent_id', 'node_type', 'is_smoke', 'exec_result', 'title', 'image')
    )
    roots = _build_tree(rows)
    if roots:
        tree = roots[0]
    else:
        tree = {
            'id': None,
            'parent_id': None,
            'node_type': 'module',
            'is_smoke': False,
            'exec_result': '',
            'title': c.case_name or '用例',
            'image': '',
            'children': [],
        }
    return JsonResponse({'code': 0, 'data': tree})


def _normalize_node(node):
    """规范化单个思维导图节点（标题/类型/子节点）。"""
    title = (node.get('title') or '').strip()
    if not title and not (node.get('image') or '').strip():
        title = '未命名'
    node_type = (node.get('node_type') or 'case').strip()
    if node_type not in NODE_TYPES:
        node_type = 'case'
    exec_result = (node.get('exec_result') or '').strip()
    if exec_result not in ('pass', 'fail'):
        exec_result = ''
    children = node.get('children') or []
    if not isinstance(children, list):
        children = []
    return {
        'title': title,
        'node_type': node_type,
        'is_smoke': bool(node.get('is_smoke')),
        'exec_result': exec_result,
        'image': (node.get('image') or '').strip(),
        'children': children,
    }


def _replace_case_nodes(case_id, tree):
    """在事务内全量替换用例的思维导图节点（tree 根节点已规范化，需在事务中调用）。"""
    def _create(node, parent, sort):
        title = node.get('title') or ''
        if not title and not (node.get('image') or ''):
            title = '未命名'
        n = ZCaseGovernCaseNode.objects.create(
            case_id=case_id,
            parent=parent,
            node_type=node.get('node_type') or 'case',
            is_smoke=bool(node.get('is_smoke')),
            exec_result=node.get('exec_result') or '',
            title=title,
            image=node.get('image') or '',
            sort_order=sort,
        )
        for i, ch in enumerate(node.get('children') or []):
            _create(ch, n, i)
        return n

    ZCaseGovernCaseNode.objects.filter(case_id=case_id).delete()
    _create(tree, None, 0)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_mind_save(request, pk):
    """保存思维导图：接收整棵树 JSON，事务内全量替换该用例的节点。"""
    try:
        case = ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)
    # 仅创建人可编辑（非创建人只能查看）
    creator = (case.creator or '').strip()
    current_user = _current_user_name(request)
    if creator and current_user and creator != current_user:
        return JsonResponse({'code': 403, 'message': '仅创建人可编辑该用例'}, status=403)
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    tree = body.get('tree') if isinstance(body, dict) else body
    if not isinstance(tree, dict):
        return JsonResponse({'code': 400, 'message': '思维导图数据格式错误'}, status=400)

    with transaction.atomic():
        _replace_case_nodes(pk, _normalize_node(tree))
        # 保存节点后同步刷新用例主表更新时间（auto_now 自动置为当前时间）
        case.save(update_fields=['update_time'])

    return JsonResponse({'code': 0, 'message': '用例已保存'})


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_node_exec(request, pk):
    """更新单个节点的执行结果（非创建人也可标记测试通过/不通过）。"""
    try:
        case = ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    node_id = body.get('node_id')
    exec_result = (body.get('exec_result') or '').strip()
    if node_id is None:
        return JsonResponse({'code': 400, 'message': '缺少 node_id'}, status=400)
    if exec_result not in ('', 'pass', 'fail'):
        return JsonResponse({'code': 400, 'message': '执行结果须为 pass/fail/空'}, status=400)
    try:
        node = ZCaseGovernCaseNode.objects.get(case_id=pk, id=node_id)
    except ZCaseGovernCaseNode.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '节点不存在'}, status=404)
    node.exec_result = exec_result
    node.save(update_fields=['exec_result', 'update_time'])
    # 同步刷新用例主表更新时间
    case.save(update_fields=['update_time'])
    return JsonResponse({'code': 0, 'message': '执行结果已更新'})


# 节点图片（base64 data URL）的 MIME 类型到文件扩展名映射
MIME_EXT = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
    'image/bmp': '.bmp',
    'image/svg+xml': '.svg',
}
# 文件扩展名到 MIME 类型的反向映射（用于 .emmx 导入时按 media 文件扩展名推断）
EXT_MIME = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
    'bmp': 'image/bmp',
    'svg': 'image/svg+xml',
}


def _parse_data_url(data_url):
    """解析 base64 data URL，返回 (mime_type, raw_bytes)；解析失败返回 (None, None)。"""
    s = (data_url or '').strip()
    if not s.startswith('data:'):
        return None, None
    try:
        meta, b64 = s.split(',', 1)
    except ValueError:
        return None, None
    # meta 形如 "data:image/png;base64" 或 "data:image/png"
    mime = 'image/png'
    header = meta[len('data:'):]
    if ';' in header:
        mime_part = header.split(';', 1)[0].strip().lower()
    else:
        mime_part = header.strip().lower()
    if mime_part.startswith('image/'):
        mime = mime_part
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None, None
    return mime, raw


# 冒烟用例按执行结果给节点文字上色：通过绿色、不通过红色（与前端 SVG 导出用色一致）
EXEC_RESULT_COLOR = {'pass': '#67c23a', 'fail': '#f56c6c'}


def _node_to_xmind_topic(node, image_srcs=None):
    """将用例节点树转为 XMind（新版 content.json）topic 结构。

    image_srcs: dict[node_id -> "xap:resources/xxx.png"]，用于给有截图的节点挂图片。
    """
    nid = node.get('id')
    title = node.get('title') or ''
    # 冒烟、执行结果以标题后缀形式展示（可靠、任何 XMind 版本均可显示）
    marks = []
    if node.get('is_smoke'):
        marks.append('冒烟')
    exec_result = node.get('exec_result') or ''
    if exec_result == 'pass':
        marks.append('通过')
    elif exec_result == 'fail':
        marks.append('不通过')
    if marks:
        title = '%s【%s】' % (title, '·'.join(marks))
    topic = {
        'id': str(nid) if nid is not None else 'root',
        'class': 'topic',
        'title': title,
        # 逻辑图（向右）：根在左、子节点向右单侧展开，与设计用例页面布局一致
        'structureClass': 'org.xmind.ui.logic.right',
    }
    # 冒烟用例执行结果给节点文字上色：fo:color 控制 XMind 主题文字颜色
    if node.get('is_smoke') and exec_result in EXEC_RESULT_COLOR:
        topic['style'] = {
            'id': 'style:%s' % topic['id'],
            'properties': {'fo:color': EXEC_RESULT_COLOR[exec_result]},
        }
    # 节点截图：作为 topic 的 image 引用（图片二进制已写入 zip 的 resources/ 目录）
    src = (image_srcs or {}).get(nid)
    if src:
        topic['image'] = {'src': src}
    children = node.get('children') or []
    if children:
        topic['children'] = {'attached': [_node_to_xmind_topic(c, image_srcs) for c in children]}
    return topic


@csrf_exempt
@require_http_methods(['GET'])
@require_valid_token
def case_export_xmind(request, pk):
    """导出用例为 .xmind 思维导图文件（ZIP 内含新版 content.json）。"""
    try:
        case = ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)

    rows = list(
        ZCaseGovernCaseNode.objects.filter(case_id=pk)
        .order_by('sort_order', 'id')
        .values('id', 'parent_id', 'node_type', 'is_smoke', 'exec_result', 'title', 'image')
    )
    roots = _build_tree(rows)
    if roots:
        root = roots[0]
    else:
        root = {'id': None, 'title': case.case_name or '用例', 'children': []}

    # 收集节点截图：解析 base64 data URL，写入 zip 的 resources/ 目录，
    # 同一张图片（按内容 hash 去重）只写一份。
    image_srcs = {}
    resource_files = {}
    for r in rows:
        mime, raw = _parse_data_url(r.get('image') or '')
        if not raw:
            continue
        filename = hashlib.sha256(raw).hexdigest() + MIME_EXT.get(mime, '.png')
        path = 'resources/%s' % filename
        resource_files[path] = raw
        image_srcs[r['id']] = 'xap:%s' % path

    sheet = {
        'id': '%s-sheet' % pk,
        'class': 'sheet',
        'title': case.case_name or '用例',
        'rootTopic': _node_to_xmind_topic(root, image_srcs),
    }
    metadata = {'creator': {'name': case.creator or '', 'version': '1.0.0'}}
    manifest = {'file-entries': {'content.json': {}, 'metadata.json': {}}}
    for path in resource_files:
        manifest['file-entries'][path] = {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('content.json', json.dumps([sheet], ensure_ascii=False))
        zf.writestr('metadata.json', json.dumps(metadata, ensure_ascii=False))
        zf.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        for path, data in resource_files.items():
            zf.writestr(path, data)
    buf.seek(0)

    filename = quote((case.case_name or '用例') + '.xmind')
    resp = HttpResponse(buf.read(), content_type='application/vnd.xmind.workbook')
    resp['Content-Disposition'] = "attachment; filename*=UTF-8''%s" % filename
    return resp


# ── .emmx（MindMaster 思维导图）导入 ──────────────────────────────

def _extract_emmx_text(shape):
    """提取 Shape 内所有 <tp> 文本并折叠空白。"""
    parts = [tp.text or '' for tp in shape.iter('tp')]
    return re.sub(r'\s+', ' ', ''.join(parts)).strip()


def _parse_emmx_rels(zf):
    """解析 .emmx 关系文件（rels/*.xml），返回 {rId: zip 内 media 路径}。"""
    rel_map = {}
    rel_names = [
        n for n in zf.namelist()
        if n.lower().startswith('rels/') and n.lower().endswith('.xml')
    ]
    for rel_name in rel_names:
        try:
            rel_root = ET.fromstring(zf.read(rel_name))
        except ET.ParseError:
            continue
        rel_dir = posixpath.dirname(rel_name)
        for rel in rel_root.iter('Relationship'):
            rid = rel.get('Id')
            target = rel.get('Target')
            if not rid or not target:
                continue
            # target 是相对 rels 文件所在目录的路径，规范化为 zip 内路径
            rel_map[rid] = posixpath.normpath(posixpath.join(rel_dir, target))
    return rel_map


def _extract_emmx_image(shape, rel_map, media_data):
    """提取 Shape 内图片，返回 base64 data URL；无图片返回空字符串。"""
    for img in shape.iter('Image'):
        rid = img.get('Name') or img.get('Id')
        if not rid:
            continue
        path = rel_map.get(rid)
        if not path or path not in media_data:
            continue
        ext = posixpath.splitext(path)[1].lower().lstrip('.')
        mime = EXT_MIME.get(ext, 'image/png')
        return 'data:%s;base64,%s' % (mime, base64.b64encode(media_data[path]).decode('ascii'))
    return ''


def _parse_emmx(raw_bytes):
    """解析 .emmx 文件（ZIP 内含思维导图 XML），返回 (topics, root)。"""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith('.xml')]
        ordered = [n for n in ('page/page.xml', 'document.xml') if n in names]
        ordered += [n for n in names if n not in ordered]
        xml_bytes = None
        for name in ordered:
            data = zf.read(name)
            if b'MainIdea' in data or b'MainTopic' in data:
                xml_bytes = data
                break
        if xml_bytes is None:
            raise ValueError('未找到思维导图内容（MainIdea/MainTopic）')

        # 解析关系文件并预读所有 media 图片（在 zip 关闭前完成读取）
        rel_map = _parse_emmx_rels(zf)
        media_data = {}
        for path in set(rel_map.values()):
            try:
                media_data[path] = zf.read(path)
            except KeyError:
                continue

    try:
        page = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError('思维导图 XML 解析失败：%s' % e)

    topics = {}
    for shape in page.iter('Shape'):
        typ = shape.get('Type') or ''
        if typ not in ('MainIdea', 'MainTopic', 'SubTopic'):
            continue
        sid = shape.get('ID')
        if not sid:
            continue
        super_id = None
        subs = []
        ld = shape.find('LevelData')
        if ld is not None:
            s = ld.find('Super')
            if s is not None:
                super_id = s.get('V')
            sl = ld.find('SubLevel')
            if sl is not None:
                subs = [x for x in (sl.get('V') or '').split(';') if x]
        text = _extract_emmx_text(shape)
        image = _extract_emmx_image(shape, rel_map, media_data)
        # 图片节点：MindMaster 用占位文本 "p" 表示（节点仅含图片、无文字），清空避免展示 "p"
        if image and text == 'p':
            text = ''
        topics[sid] = {
            'id': sid,
            'typ': typ,
            'text': text,
            'super': super_id,
            'subs': subs,
            'image': image,
        }

    root = next((t for t in topics.values() if t['typ'] == 'MainIdea'), None)
    if root is None:
        raise ValueError('未找到思维导图根主题（MainIdea）')
    return topics, root


def _xmind_local(tag):
    """去掉 XML 命名空间前缀，返回本地标签名。"""
    return tag.rsplit('}', 1)[-1]


def _parse_xmind_xml(xml_bytes):
    """解析 .xmind 旧版格式（content.xml），返回 (topics, root)。"""
    try:
        root_el = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError('思维导图 XML 解析失败：%s' % e)

    for sheet in root_el.iter():
        if _xmind_local(sheet.tag) != 'sheet':
            continue
        root_topic_el = next((c for c in sheet if _xmind_local(c.tag) == 'topic'), None)
        if root_topic_el is None:
            continue

        topics = {}

        def add(topic_el):
            tid = topic_el.get('id') or ''
            if not tid:
                return
            title_el = next((c for c in topic_el if _xmind_local(c.tag) == 'title'), None)
            text = re.sub(r'\s+', ' ', ''.join(title_el.itertext())) if title_el is not None else ''
            topics[tid] = {'id': tid, 'text': text.strip(), 'subs': []}

        for topic_el in sheet.iter():
            if _xmind_local(topic_el.tag) == 'topic':
                add(topic_el)

        for topic_el in sheet.iter():
            if _xmind_local(topic_el.tag) != 'topic':
                continue
            tid = topic_el.get('id')
            if not tid or tid not in topics:
                continue
            subs = []
            for children_el in topic_el:
                if _xmind_local(children_el.tag) != 'children':
                    continue
                for topics_el in children_el:
                    if _xmind_local(topics_el.tag) != 'topics':
                        continue
                    for sub_el in topics_el:
                        if _xmind_local(sub_el.tag) == 'topic' and sub_el.get('id') in topics:
                            subs.append(sub_el.get('id'))
            topics[tid]['subs'] = subs

        root = topics.get(root_topic_el.get('id'))
        if root:
            return topics, root
    raise ValueError('未找到思维导图根主题（sheet/topic）')


def _parse_xmind_json(json_bytes):
    """解析 .xmind 新版格式（content.json），返回 (topics, root)。"""
    try:
        data = json.loads(json_bytes.decode('utf-8'))
    except Exception as e:
        raise ValueError('思维导图 JSON 解析失败：%s' % e)

    sheets = [data] if isinstance(data, dict) else (data if isinstance(data, list) else [])

    def json_children(t):
        children = t.get('children') if isinstance(t, dict) else None
        result = []
        if isinstance(children, dict):
            for group in children.values():
                if isinstance(group, list):
                    result.extend(group)
        elif isinstance(children, list):
            result.extend(children)
        return result

    topics = {}

    def collect(t):
        if not isinstance(t, dict):
            return None
        tid = t.get('id') or ''
        title = t.get('title') or ''
        if isinstance(title, dict):
            title = title.get('text') or ''
        text = re.sub(r'\s+', ' ', str(title)).strip()
        topics[tid] = {'id': tid, 'text': text, 'subs': []}
        for child in json_children(t):
            cid = collect(child)
            if cid and cid in topics:
                topics[tid]['subs'].append(cid)
        return tid

    for sheet in sheets:
        if not isinstance(sheet, dict):
            continue
        root_topic = sheet.get('rootTopic')
        if not isinstance(root_topic, dict):
            continue
        root_id = collect(root_topic)
        if root_id and root_id in topics:
            return topics, topics[root_id]
    raise ValueError('未找到思维导图根主题（sheet/rootTopic）')


def _parse_xmind(raw_bytes):
    """解析 .xmind 文件（ZIP 内含 content.json 或 content.xml），返回 (topics, root)。"""
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = {n.lower(): n for n in zf.namelist()}
        if 'content.json' in names:
            return _parse_xmind_json(zf.read(names['content.json']))
        if 'content.xml' in names:
            return _parse_xmind_xml(zf.read(names['content.xml']))
    raise ValueError('未找到思维导图内容（content.json/content.xml）')


def _topics_to_tree(topics, root):
    """将思维导图主题扁平表转成思维导图树，按层级映射节点类型。"""
    def build(tid, depth):
        t = topics[tid]
        text = t['text'] or ''
        image = t.get('image') or ''
        # 纯图片节点（无文字、有图片）标题保持为空，仅文字与图片都缺失时补「未命名」
        if not text and not image:
            text = '未命名'
        return {
            'title': text,
            'node_type': IMPORT_DEPTH_TYPE.get(depth, 'case'),
            'is_smoke': False,
            'exec_result': '',
            'image': image,
            'children': [build(cid, depth + 1) for cid in t['subs'] if cid in topics],
        }

    return build(root['id'], 0)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_import(request):
    """导入思维导图（.emmx / .xmind）：根据文件扩展名自动区分解析方式并创建用例及节点。"""
    uploaded = request.FILES.get('file')
    if not uploaded:
        return JsonResponse({'code': 400, 'message': '未检测到上传文件'}, status=400)
    name = uploaded.name or ''
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    parser = {'xmind': _parse_xmind, 'emmx': _parse_emmx}.get(ext)
    if parser is None:
        return JsonResponse({'code': 400, 'message': '仅支持 .emmx / .xmind 思维导图文件'}, status=400)

    try:
        topics, root = parser(uploaded.read())
    except zipfile.BadZipFile:
        return JsonResponse({'code': 400, 'message': '不是有效的 .%s 文件（ZIP 解压失败）' % ext}, status=400)
    except ValueError as e:
        return JsonResponse({'code': 400, 'message': '解析失败：%s' % e}, status=400)
    except Exception as e:
        logger.exception('导入 %s 失败: %s', ext, name)
        return JsonResponse({'code': 500, 'message': '导入失败：%s' % e}, status=500)

    fallback_name = name.rsplit('.', 1)[0] if '.' in name else name
    case_name = root['text'] or fallback_name
    module = IMPORT_DEFAULT_MODULE
    if ZCaseGovernCase.objects.filter(case_name=case_name, module=module).exists():
        return JsonResponse(
            {'code': 400, 'message': '已存在同名用例「%s」，请先删除或重命名后再导入' % case_name},
            status=400,
        )

    tree = _topics_to_tree(topics, root)
    with transaction.atomic():
        c = ZCaseGovernCase.objects.create(
            case_name=case_name,
            module=module,
            priority=2,
            status=1,
            creator=_current_user_name(request),
            description='',
            image='',
        )
        _replace_case_nodes(c.id, _normalize_node(tree))

    _ensure_module(module)
    node_count = ZCaseGovernCaseNode.objects.filter(case_id=c.id).count()
    return JsonResponse({'code': 0, 'message': '导入成功', 'data': _serialize_case(c, node_count)})


# 兼容旧接口名（.emmx 导入入口），与新统一入口行为一致
case_import_emmx = case_import
