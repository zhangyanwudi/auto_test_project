# -*- coding: utf-8 -*-
"""
页面巡检任务入口（debug_task.sh 可直接调用）

子命令：
  explore  用 AI 按文字目标探索页面，生成/更新 page_patrol 下的 JSON
  run      按 JSON 中的 run 参数在浏览器中回放（不调用 AI）

用法（在 backend 目录下）：
  # 1. AI 探索并生成 JSON（会打开浏览器，AI 按目标文字查找元素）
  ./debug_task.sh page_patrol_task.py explore \
      --goal "达人管理--上传达人--单个上传，昵称填{{user_name}}，上传达人批量模板，点击保存，列表出现{{user_name}}" \
      --json page_patrol/达人管理-上传达人-单个上传.json \
      --input 昵称={{user_name}} \
      --filter 达人昵称=ZnYan

  # 2. 检查计划（不打开浏览器）
  ./debug_task.sh page_patrol_task.py run --json page_patrol/达人管理-上传达人-单个上传.json --dry-run

  # 3. 按 JSON 执行
  ./debug_task.sh page_patrol_task.py run --json page_patrol/达人管理-上传达人-单个上传.json

参数值全部写在 JSON 的 run 块中，命令行只用于指定文件与模式。
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

DEFAULT_JSON = os.path.join(BACKEND, 'page_patrol', '达人管理-上传达人-单个上传.json')


def _kv(items):
    out = {}
    for it in items or []:
        if '=' not in it:
            raise SystemExit(f'参数格式应为 键=值：{it}')
        k, v = it.split('=', 1)
        out[k.strip()] = v.strip()
    return out


def cmd_explore(args):
    ok, out, err = explore_to_json(
        args.goal, args.json, run_inputs=_kv(args.input), run_filters=_kv(args.filter),
        on_progress=lambda t: print(t, flush=True),
    )
    if not ok:
        print(f'❌ 探索失败：{err}')
        return 1
    print(f'✅ 已生成 JSON：{out}')
    print('请检查 JSON 中的 pages 与 run 后，再用 run 子命令执行。')
    return 0


def cmd_run(args):
    if not os.path.isfile(args.json):
        print(f'❌ JSON 文件不存在：{args.json}')
        return 1
    data = patrol_core.load_json(args.json)
    plan, errors = patrol_core.validate(data)
    print('执行计划：')
    for line in plan:
        print('  - ' + line)
    if errors:
        print('❌ 校验失败：')
        for e in errors:
            print('  - ' + e)
        return 1
    print('✅ JSON 与 run 参数校验通过')
    if args.dry_run:
        return 0
    rep = patrol_core.execute(data, upload_path=args.upload, headless=args.headless)
    if rep['ok']:
        print('结果：通过 ✅')
        return 0
    print(f'结果：失败 ❌（唯一标识 {rep["marker"]}）：{rep["error"]}')
    if rep.get('screenshot'):
        print(f'失败截图：{rep["screenshot"]}')
    return 1


def main():
    ap = argparse.ArgumentParser(description='页面巡检任务')
    sub = ap.add_subparsers(dest='cmd', required=True)

    e = sub.add_parser('explore', help='AI 探索并生成 JSON')
    e.add_argument('--goal', required=True, help='目标文字，层级用 -- 分隔')
    e.add_argument('--json', default=DEFAULT_JSON, help='输出 JSON 路径')
    e.add_argument('--input', action='append', help='run.inputs 键=值，可多次传入')
    e.add_argument('--filter', action='append', help='run.filters 键=值，可多次传入')
    e.set_defaults(func=cmd_explore)

    r = sub.add_parser('run', help='按 JSON 执行')
    r.add_argument('--json', default=DEFAULT_JSON, help='JSON 路径')
    r.add_argument('--dry-run', action='store_true', help='只检查计划，不打开浏览器')
    r.add_argument('--upload', default='', help='上传文件路径（默认 runner 配置）')
    r.add_argument('--headless', action='store_true', help='无界面运行（默认可见浏览器）')
    r.set_defaults(func=cmd_run)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
