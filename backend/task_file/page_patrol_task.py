# -*- coding: utf-8 -*-
"""
页面巡检统一入口（debug_task.sh 可直接调用）

子命令：
  explore  用 AI 按文字目标探索页面，生成/更新模块 JSON（page_patrol/examples 下）
  case     执行 page_patrol/cases 下的 case 文件（只读模块 JSON，不调用 AI）

用法（在 backend 目录下）：
  # 1. AI 探索并生成模块 JSON（会打开浏览器）
  ./debug_task.sh page_patrol_task.py explore \
      --goal "达人管理--上传达人--单个上传，……" \
      --json page_patrol/examples/达人管理.example.json

  # 2. 执行 case（--dry-run 只检查计划，不打开浏览器）
  ./debug_task.sh page_patrol_task.py case --case 达人管理-上传达人-单个上传.py --dry-run
  ./debug_task.sh page_patrol_task.py case --case 达人管理-上传达人-单个上传.py

录入数据写在模块 JSON 的 operations.<操作>.data 中，case 只指定目标与执行方式。
"""
import argparse
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django  # noqa: E402

django.setup()

from page_patrol import patrol_core  # noqa: E402
from page_patrol.explore import explore_to_json  # noqa: E402

CASES_DIR = os.path.join(BACKEND, 'page_patrol', 'cases')


def cmd_explore(args):
    ok, out, err = explore_to_json(args.goal, args.json, on_progress=lambda t: print(t, flush=True))
    if not ok:
        print(f'❌ 探索失败：{err}')
        return 1
    print(f'✅ 已生成 JSON：{out}')
    print('请检查 JSON 后，再用 case 子命令执行。')
    return 0


def _run_data(data, dry_run, upload='', headless=False, post_check=None, response_watch=None):
    """校验并执行一份（已补全 run 的）JSON。返回 (退出码, 执行报告或 None)。"""
    plan, errors = patrol_core.validate(data)
    print('执行计划：')
    for line in plan:
        print('  - ' + line)
    if errors:
        print('❌ 校验失败：')
        for e in errors:
            print('  - ' + e)
        return 1, None
    print('✅ JSON 与 run 参数校验通过')
    if dry_run:
        return 0, None
    rep = patrol_core.execute(data, upload_path=upload, headless=headless, post_check=post_check,
                              response_watch=response_watch)
    if rep['ok']:
        print('结果：通过 ✅')
        return 0, rep
    print(f'结果：失败 ❌（唯一标识 {rep["marker"]}）：{rep["error"]}')
    if rep.get('screenshot'):
        print(f'失败截图：{rep["screenshot"]}')
    return 1, rep


def _load_case(name):
    import importlib.util
    name = os.path.basename(name)
    if not name.endswith('.py'):
        name += '.py'
    path = os.path.join(CASES_DIR, name)
    if not os.path.isfile(path):
        return None, name
    spec = importlib.util.spec_from_file_location(f'case_{name[:-3]}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, name


def run_case(name, dry_run=False, upload='', headless=False, order_type=None, chained=False):
    """执行 case；上传达人成功后，若 case 声明了 CHAIN_NEXT，则写入缓存并调用下一个 case。"""
    mod, name = _load_case(name)
    if mod is None:
        print(f'❌ 未找到 case 文件：{name}')
        print('可选 case：' + '、'.join(sorted(f for f in os.listdir(CASES_DIR) if f.endswith('.py'))))
        return 1
    base = patrol_core.load_json(os.path.join(BACKEND, 'page_patrol', mod.JSON_PATH_IN_EXAMPLES))
    print(f'Case：{mod.CASE_NAME}（保存开关 SAVE_ENABLED={mod.SAVE_ENABLED}）')
    try:
        data = mod.build(base, order_type=order_type, chained=chained) if hasattr(mod, 'resolve_nickname') else mod.build(base)
    except ValueError as e:
        print(f'❌ {e}')
        return 1
    post = None
    watch = getattr(mod, 'RESPONSE_WATCH', None)
    if getattr(mod, 'SAVE_ENABLED', False) and hasattr(mod, 'make_post_check'):
        nickname, expect_type = mod.expected(order_type=order_type, chained=chained)
        post = mod.make_post_check(data, nickname, expect_type)
    code, rep = _run_data(data, dry_run, upload, headless, post_check=post, response_watch=watch)
    if code == 0 and rep and getattr(mod, 'CHAIN_NEXT', None):
        from base_utils.persist_base import PersistBase
        ops = base['pages']['上传达人']['operations']['单个上传']['data']
        upload_type = ops['其他信息']['达人类型']
        PersistBase(mod.CACHE_NAME).put(mod.CACHE_KEY, {'nickname': rep['marker'], '达人类型': upload_type})
        print(f'✅ 已缓存上传结果（唯一标识 {rep["marker"]}，达人类型 {upload_type}），调用 {mod.CHAIN_NEXT}')
        return run_case(mod.CHAIN_NEXT, dry_run=dry_run, upload=upload, headless=headless, chained=True)
    return code


def cmd_case(args):
    """执行 page_patrol/cases 下的 case 文件：--case 文件名（可带或不带 .py）。"""
    return run_case(args.case, dry_run=args.dry_run, upload=args.upload, headless=args.headless,
                    order_type=args.order_type)


def main():
    ap = argparse.ArgumentParser(description='页面巡检任务')
    sub = ap.add_subparsers(dest='cmd', required=True)

    e = sub.add_parser('explore', help='AI 探索并生成模块 JSON')
    e.add_argument('--goal', required=True, help='目标文字，层级用 -- 分隔')
    e.add_argument('--json', required=True, help='输出模块 JSON 路径')
    e.set_defaults(func=cmd_explore)

    c = sub.add_parser('case', help='执行 page_patrol/cases 下的 case 文件')
    c.add_argument('--case', required=True, help='case 文件名，如 达人管理-上传达人-单个上传.py')
    c.add_argument('--dry-run', action='store_true', help='只检查计划，不打开浏览器')
    c.add_argument('--upload', default='', help='上传文件路径（默认 runner 配置）')
    c.add_argument('--headless', action='store_true', help='无界面运行（默认可见浏览器）')
    c.add_argument('--order_type', default=None, choices=['koc', 'kol'], help='创建订单 case 直接执行时必填：koc 或 kol')
    c.set_defaults(func=cmd_case)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
