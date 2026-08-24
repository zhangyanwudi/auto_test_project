import io
import json
import logging
import re
import zipfile
import xml.etree.ElementTree as ET

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.case_govern.models import ZCaseGovernCase, ZCaseGovernCaseNode, ZCaseGovernModule
from apps.users.decorators import require_valid_token

logger = logging.getLogger('apis.case_govern')

NODE_TYPES = ('module', 'case', 'step', 'expect', 'precondition')
PRIORITY_MAP = {1: '高', 2: '中', 3: '低'}
# 导入 .emmx 时按层级映射节点类型：0-根主题(模块)，其余层级统一映射为用例
EMMX_DEPTH_TYPE = {0: 'module'}
# 导入 .emmx 时用例归属模块（文件不含模块信息，归入「其它」）
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
        ZCaseGovernCase.objects.get(pk=pk)
    except ZCaseGovernCase.DoesNotExist:
        return JsonResponse({'code': 404, 'message': '用例不存在'}, status=404)
    body = _parse_body(request)
    if body is None:
        return JsonResponse({'code': 400, 'message': '请求体格式错误'}, status=400)
    tree = body.get('tree') if isinstance(body, dict) else body
    if not isinstance(tree, dict):
        return JsonResponse({'code': 400, 'message': '思维导图数据格式错误'}, status=400)

    with transaction.atomic():
        _replace_case_nodes(pk, _normalize_node(tree))

    return JsonResponse({'code': 0, 'message': '思维导图已保存'})


# ── .emmx（MindMaster 思维导图）导入 ──────────────────────────────

def _extract_emmx_text(shape):
    """提取 Shape 内所有 <tp> 文本并折叠空白。"""
    parts = [tp.text or '' for tp in shape.iter('tp')]
    return re.sub(r'\s+', ' ', ''.join(parts)).strip()


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
        topics[sid] = {
            'id': sid,
            'typ': typ,
            'text': _extract_emmx_text(shape),
            'super': super_id,
            'subs': subs,
        }

    root = next((t for t in topics.values() if t['typ'] == 'MainIdea'), None)
    if root is None:
        raise ValueError('未找到思维导图根主题（MainIdea）')
    return topics, root


def _emmx_to_tree(topics, root):
    """将 .emmx 主题扁平表转成思维导图树，按层级映射节点类型。"""
    def build(tid, depth):
        t = topics[tid]
        return {
            'title': t['text'] or '未命名',
            'node_type': EMMX_DEPTH_TYPE.get(depth, 'case'),
            'is_smoke': False,
            'exec_result': '',
            'image': '',
            'children': [build(cid, depth + 1) for cid in t['subs'] if cid in topics],
        }

    return build(root['id'], 0)


@csrf_exempt
@require_http_methods(['POST'])
@require_valid_token
def case_import_emmx(request):
    """导入 MindMaster（.emmx）思维导图：解析主题树并创建用例及节点。"""
    uploaded = request.FILES.get('file')
    if not uploaded:
        return JsonResponse({'code': 400, 'message': '未检测到上传文件'}, status=400)
    if not (uploaded.name or '').lower().endswith('.emmx'):
        return JsonResponse({'code': 400, 'message': '仅支持 .emmx 思维导图文件'}, status=400)

    try:
        topics, root = _parse_emmx(uploaded.read())
    except zipfile.BadZipFile:
        return JsonResponse({'code': 400, 'message': '不是有效的 .emmx 文件（ZIP 解压失败）'}, status=400)
    except ValueError as e:
        return JsonResponse({'code': 400, 'message': '解析失败：%s' % e}, status=400)
    except Exception as e:
        logger.exception('导入 emmx 失败: %s', uploaded.name)
        return JsonResponse({'code': 500, 'message': '导入失败：%s' % e}, status=500)

    fallback_name = uploaded.name.rsplit('.', 1)[0] if '.' in uploaded.name else uploaded.name
    case_name = root['text'] or fallback_name
    module = IMPORT_DEFAULT_MODULE
    if ZCaseGovernCase.objects.filter(case_name=case_name, module=module).exists():
        return JsonResponse(
            {'code': 400, 'message': '已存在同名用例「%s」，请先删除或重命名后再导入' % case_name},
            status=400,
        )

    tree = _emmx_to_tree(topics, root)
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
