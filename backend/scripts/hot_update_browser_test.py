#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
热更测试 - 浏览器自动化脚本

功能：
1. 使用 Playwright 无痕模式启动浏览器
2. 打开配置比对页面
3. 根据项目选择对应项目
4. 在左侧和右侧分别录入方案号
5. 获取两个方案的 JSON 配置
6. 深度对比两个 JSON
7. 校验差异是否与文档中的修改范围一致

用法：
    python3 scripts/hot_update_browser_test.py \\
        --project gp_blockblast_orth \\
        --left-scheme rv623601 \\
        --right-scheme rv8175705 \\
        --modification-scope "root.ad_unit_1.reload.reload_count,root.ad_unit_1.reload.reload_logic.retry_intervals" \\
        --frontend-url http://localhost:5173 \\
        [--output result.json]

依赖：
    pip install playwright
    playwright install chromium

输出格式（JSON）：
{
    "success": true,
    "project": "gp_blockblast_orth",
    "left_scheme": "rv623601",
    "right_scheme": "rv8175705",
    "diff": {
        "key_diff": {...},
        "value_diffs": [...]
    },
    "modification_check": {
        "expected_changes": [...],
        "unexpected_changes": [...],
        "missing_changes": [...]
    },
    "summary": "..."
}
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# ============================================================
# 页面元素选择器配置（需根据前端实际页面结构调整）
# ============================================================
PAGE_SELECTORS = {
    # 项目下拉框
    'project_select': '#project-select, [data-testid="project-select"], .project-dropdown select',
    # 项目下拉选项（根据项目名匹配）
    'project_option': 'option, .el-select-dropdown__item, [role="option"]',
    # 左侧方案号搜索输入框
    'left_search_input': '#left-search-input, [data-testid="left-search"], .left-panel .search-input input',
    # 左侧方案搜索结果列表
    'left_search_results': '.left-panel .search-results, [data-testid="left-results"]',
    # 左侧方案 JSON 展示区域
    'left_json_area': '#left-json-viewer, [data-testid="left-json"], .left-panel .json-content',
    # 右侧方案号搜索输入框
    'right_search_input': '#right-search-input, [data-testid="right-search"], .right-panel .search-input input',
    # 右侧方案搜索结果列表
    'right_search_results': '.right-panel .search-results, [data-testid="right-results"]',
    # 右侧方案 JSON 展示区域
    'right_json_area': '#right-json-viewer, [data-testid="right-json"], .right-panel .json-content',
    # 加载指示器
    'loading_indicator': '.loading-spinner, .el-loading-mask, [data-testid="loading"]',
    # 错误提示
    'error_message': '.error-message, .el-message--error, [data-testid="error"]',
}


def parse_args():
    parser = argparse.ArgumentParser(
        description='热更测试 - 配置比对浏览器自动化',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/hot_update_browser_test.py \\
      --project gp_blockblast_orth \\
      --left-scheme rv623601 \\
      --right-scheme rv8175705 \\
      --modification-scope "path.to.field1,path.to.field2" \\
      --frontend-url http://localhost:5173
        """,
    )
    parser.add_argument('--project', required=True, help='项目内部标识（如 gp_blockblast_orth）')
    parser.add_argument('--left-scheme', required=True, help='左侧方案号')
    parser.add_argument('--right-scheme', required=True, help='右侧方案号')
    parser.add_argument('--modification-scope', default='', help='预期修改范围，逗号分隔的路径列表')
    parser.add_argument('--frontend-url', default='http://localhost:5173', help='前端页面地址')
    parser.add_argument('--page-path', default='/config-compare', help='配置比对页面路径')
    parser.add_argument('--headless', action='store_true', default=True, help='无头模式（默认开启）')
    parser.add_argument('--no-headless', action='store_true', help='显示浏览器窗口（调试用）')
    parser.add_argument('--output', '-o', help='输出结果到 JSON 文件')
    parser.add_argument('--timeout', type=int, default=30000, help='操作超时（毫秒，默认 30000）')
    parser.add_argument('--selectors-config', help='自定义选择器配置 JSON 文件路径')
    return parser.parse_args()


# ============================================================
# JSON 对比工具（复用 base_utils/json_utils 逻辑）
# ============================================================

def _get_key_structure(obj: Any, path: str = "") -> Set[str]:
    """递归获取 JSON 对象的所有 key 路径结构。"""
    keys = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            current_path = f"{path}.{key}" if path else key
            keys.add(current_path)
            if isinstance(value, (dict, list)) and value:
                keys.update(_get_key_structure(value, current_path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, (dict, list)):
                list_path = f"{path}[]"
                keys.update(_get_key_structure(item, list_path))
                break
    return keys


def compare_json_structure(json1: Any, json2: Any) -> dict:
    """比对两个 JSON 结构的 key 差异。"""
    keys1 = _get_key_structure(json1, "root")
    keys2 = _get_key_structure(json2, "root")
    return {
        "is_identical": keys1 == keys2,
        "only_in_first": sorted(keys1 - keys2),
        "only_in_second": sorted(keys2 - keys1),
        "common_keys": sorted(keys1 & keys2),
        "total_keys_first": len(keys1),
        "total_keys_second": len(keys2),
    }


def _compare_values(obj1: Any, obj2: Any, path: str = "") -> List[dict]:
    """递归比较两个 JSON 对象的 value 差异。"""
    diffs = []
    if isinstance(obj1, dict) and isinstance(obj2, dict):
        all_keys = set(obj1.keys()) | set(obj2.keys())
        for key in sorted(all_keys):
            current_path = f"{path}.{key}" if path else key
            if key not in obj1:
                diffs.append({
                    "path": current_path, "type": "only_in_second",
                    "value_1": None, "value_2": obj2[key],
                })
            elif key not in obj2:
                diffs.append({
                    "path": current_path, "type": "only_in_first",
                    "value_1": obj1[key], "value_2": None,
                })
            else:
                v1, v2 = obj1[key], obj2[key]
                if isinstance(v1, (dict, list)) and isinstance(v2, (dict, list)):
                    diffs.extend(_compare_values(v1, v2, current_path))
                elif v1 != v2:
                    diffs.append({
                        "path": current_path, "type": "value_changed",
                        "value_1": v1, "value_2": v2,
                    })
    elif isinstance(obj1, list) and isinstance(obj2, list):
        max_len = max(len(obj1), len(obj2))
        for i in range(max_len):
            current_path = f"{path}[{i}]"
            if i >= len(obj1):
                diffs.append({
                    "path": current_path, "type": "only_in_second",
                    "value_1": None, "value_2": obj2[i],
                })
            elif i >= len(obj2):
                diffs.append({
                    "path": current_path, "type": "only_in_first",
                    "value_1": obj1[i], "value_2": None,
                })
            else:
                v1, v2 = obj1[i], obj2[i]
                if isinstance(v1, (dict, list)) and isinstance(v2, (dict, list)):
                    diffs.extend(_compare_values(v1, v2, current_path))
                elif v1 != v2:
                    diffs.append({
                        "path": current_path, "type": "value_changed",
                        "value_1": v1, "value_2": v2,
                    })
    else:
        if obj1 != obj2:
            diffs.append({
                "path": path, "type": "value_changed",
                "value_1": obj1, "value_2": obj2,
            })
    return diffs


def check_modification_scope(value_diffs: List[dict], expected_scope: List[str]) -> dict:
    """
    将实际的差异路径与预期的修改范围进行比对。

    参数:
        value_diffs — 实际差异列表
        expected_scope — 预期修改路径列表（支持通配符 *）

    返回:
        dict — {expected_changes, unexpected_changes, missing_changes}
    """
    # 提取所有实际差异的路径
    actual_diff_paths = {d['path'] for d in value_diffs}

    # 展开通配符路径为精确匹配
    expected_paths_set: Set[str] = set()
    for scope_path in expected_scope:
        scope_path = scope_path.strip()
        if not scope_path:
            continue
        if '*' in scope_path:
            # 通配符匹配：如 root.ad_unit_*.reload.*
            import re as _re
            pattern = scope_path.replace('.', r'\.').replace('*', r'[^.]+')
            # 同时匹配数组索引形式
            pattern = pattern.replace(r'\[\]', r'\[\d+\]')
            regex = _re.compile(f'^{pattern}$')
            for actual_path in actual_diff_paths:
                # 将实际路径中的数组索引标准化后再匹配
                normalized = _re.sub(r'\[\d+\]', '[]', actual_path)
                normalized_pattern = scope_path.replace('.', r'\.').replace('[', r'\[').replace(']', r'\]').replace('*', r'[^\[\].]+')
                normalized_regex = _re.compile(f'^{normalized_pattern}$')
                if regex.match(actual_path) or normalized_regex.match(normalized):
                    expected_paths_set.add(actual_path)
        else:
            expected_paths_set.add(scope_path)

    # 分类
    expected_changes = []
    unexpected_changes = []
    for d in value_diffs:
        if d['path'] in expected_paths_set:
            expected_changes.append(d)
        else:
            # 也检查标准化后的路径（数组索引 → []）
            import re as _re
            normalized_path = _re.sub(r'\[\d+\]', '[]', d['path'])
            is_expected = False
            for ep in expected_paths_set:
                if ep == normalized_path or normalized_path == _re.sub(r'\[\d+\]', '[]', ep):
                    is_expected = True
                    break
            if is_expected:
                expected_changes.append(d)
            else:
                unexpected_changes.append(d)

    missing_changes = sorted(expected_paths_set - {d['path'] for d in expected_changes})

    return {
        "expected_changes": expected_changes,
        "unexpected_changes": unexpected_changes,
        "missing_changes": missing_changes,
    }


# ============================================================
# Playwright 浏览器自动化
# ============================================================

async def run_browser_automation(args, selectors: dict) -> dict:
    """
    执行浏览器自动化操作：
    1. 启动无痕浏览器
    2. 打开配置比对页面并选择项目
    3. 录入左右方案号并获取 JSON
    4. 返回比对结果
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "success": False,
            "error": "未安装 Playwright，请执行: pip install playwright && playwright install chromium",
        }

    result = {
        "success": False,
        "project": args.project,
        "left_scheme": args.left_scheme,
        "right_scheme": args.right_scheme,
        "timestamp": datetime.now().isoformat(),
    }

    async with async_playwright() as p:
        # 启动浏览器（无痕 / 无头 模式）
        launch_options = {
            "headless": not args.no_headless,
            "args": [
                "--incognito",  # 无痕模式
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        }
        browser = await p.chromium.launch(**launch_options)

        # 创建无痕浏览器上下文
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
        )
        page = await context.new_page()
        page.set_default_timeout(args.timeout)

        try:
            # ---- 步骤 1：打开配置比对页面 ----
            target_url = args.frontend_url.rstrip('/') + '/' + args.page_path.lstrip('/')
            print(f"[步骤 1] 打开配置比对页面: {target_url}")
            await page.goto(target_url, wait_until="networkidle")

            # ---- 步骤 2：选择项目 ----
            print(f"[步骤 2] 选择项目: {args.project}")
            project_selected = await _select_project(page, selectors, args.project)
            if not project_selected:
                return {**result, "error": f"无法选择项目 '{args.project}'，请确认项目名称正确", "success": False}

            # 等待页面稳定
            await _wait_for_loading_complete(page, selectors)

            # ---- 步骤 3：录入左侧方案号并获取 JSON ----
            print(f"[步骤 3] 左侧录入方案号: {args.left_scheme}")
            left_json = await _search_and_get_json(
                page, selectors,
                search_input_selector=selectors['left_search_input'],
                results_selector=selectors['left_search_results'],
                json_area_selector=selectors['left_json_area'],
                scheme=args.left_scheme,
                side="left",
            )
            if left_json is None:
                return {**result, "error": f"左侧方案号 '{args.left_scheme}' 获取 JSON 失败", "success": False}
            result["left_json"] = left_json

            # ---- 步骤 4：录入右侧方案号并获取 JSON ----
            print(f"[步骤 4] 右侧录入方案号: {args.right_scheme}")
            right_json = await _search_and_get_json(
                page, selectors,
                search_input_selector=selectors['right_search_input'],
                results_selector=selectors['right_search_results'],
                json_area_selector=selectors['right_json_area'],
                scheme=args.right_scheme,
                side="right",
            )
            if right_json is None:
                return {**result, "error": f"右侧方案号 '{args.right_scheme}' 获取 JSON 失败", "success": False}
            result["right_json"] = right_json

            # ---- 步骤 5：JSON 对比 ----
            print("[步骤 5] 对比两个 JSON 配置...")
            key_diff = compare_json_structure(left_json, right_json)
            value_diffs = _compare_values(left_json, right_json)
            result["diff"] = {
                "key_diff": key_diff,
                "value_diffs": value_diffs,
                "is_identical": key_diff["is_identical"] and len(value_diffs) == 0,
            }

            # ---- 步骤 6：校验修改范围 ----
            modification_scope = _parse_modification_scope(args.modification_scope)
            if modification_scope:
                print(f"[步骤 6] 校验修改范围: {modification_scope}")
                modification_check = check_modification_scope(value_diffs, modification_scope)
                result["modification_check"] = modification_check

                # 生成总结
                expected_count = len(modification_check["expected_changes"])
                unexpected_count = len(modification_check["unexpected_changes"])
                missing_count = len(modification_check["missing_changes"])
                result["summary"] = (
                    f"差异总数: {len(value_diffs)} 处 | "
                    f"预期内变更: {expected_count} 处 | "
                    f"预期外变更: {unexpected_count} 处 | "
                    f"未发生的预期变更: {missing_count} 处"
                )
            else:
                print("[步骤 6] 未提供修改范围，跳过校验")
                result["summary"] = f"差异总数: {len(value_diffs)} 处（未提供修改范围进行校验）"

            result["success"] = True
            print(f"[完成] {result['summary']}")

        except Exception as e:
            result["success"] = False
            result["error"] = f"浏览器自动化执行异常: {e}"
            print(f"[错误] {result['error']}")

            # 截图保存（用于排查问题）
            try:
                screenshot_path = f"hot_update_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                await page.screenshot(path=screenshot_path, full_page=True)
                result["error_screenshot"] = screenshot_path
                print(f"[截图] 错误截图已保存: {screenshot_path}")
            except Exception:
                pass

        finally:
            await context.close()
            await browser.close()

    return result


async def _select_project(page, selectors: dict, project: str) -> bool:
    """在页面中选择项目。"""
    # 尝试点击项目下拉框
    try:
        await page.click(selectors['project_select'])
        await asyncio.sleep(0.5)
    except Exception:
        pass  # 可能已经展开

    # 在选项中找到并点击目标项目
    # 尝试多种选择器组合
    try:
        options = page.locator(selectors['project_option'])
        count = await options.count()
        for i in range(count):
            option = options.nth(i)
            text = await option.inner_text()
            if project.lower() in text.lower().strip():
                await option.click()
                await asyncio.sleep(0.5)
                return True
    except Exception:
        pass

    # 兜底：尝试直接通过文本定位
    try:
        await page.get_by_text(project, exact=False).first.click()
        return True
    except Exception:
        pass

    return False


async def _search_and_get_json(
    page,
    selectors: dict,
    search_input_selector: str,
    results_selector: str,
    json_area_selector: str,
    scheme: str,
    side: str,
) -> Optional[dict]:
    """
    在搜索框录入方案号并获取对应的 JSON 数据。
    """
    # 清空并输入方案号
    try:
        search_input = page.locator(search_input_selector).first
        await search_input.click()
        await search_input.fill('')
        await asyncio.sleep(0.2)
        await search_input.type(scheme, delay=50)
        await search_input.press('Enter')
    except Exception as e:
        print(f"[{side}] 录入方案号失败: {e}")
        return None

    # 等待搜索结果加载完成
    await _wait_for_loading_complete(page, selectors)
    await asyncio.sleep(1)

    # 尝试点击搜索结果中的第一项（如果需要选中）
    try:
        first_result = page.locator(results_selector).first
        if await first_result.is_visible(timeout=3000):
            await first_result.click()
            await _wait_for_loading_complete(page, selectors)
            await asyncio.sleep(1)
    except Exception:
        pass  # 可能不需要点击就已经加载

    # 获取 JSON 内容
    try:
        json_text = ""
        # 尝试从 JSON 展示区域获取文本
        json_area = page.locator(json_area_selector).first
        if await json_area.is_visible(timeout=5000):
            json_text = await json_area.inner_text()
        else:
            # 尝试从 CodeMirror 或 Monaco 编辑器中获取
            try:
                json_text = await page.locator('.CodeMirror').first.inner_text()
            except Exception:
                try:
                    json_text = await page.locator('.monaco-editor .view-lines').first.inner_text()
                except Exception:
                    pass

        if not json_text:
            print(f"[{side}] 无法获取 JSON 内容")
            return None

        # 尝试解析 JSON
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            # 可能包含额外文本，尝试提取 JSON 部分
            import re as _re
            json_match = _re.search(r'\{.*\}', json_text, _re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            print(f"[{side}] JSON 解析失败，原始内容长度: {len(json_text)}")
            return None

    except Exception as e:
        print(f"[{side}] 获取 JSON 时出错: {e}")
        return None


async def _wait_for_loading_complete(page, selectors: dict):
    """等待页面加载完成。"""
    try:
        # 等待 loading 指示器消失
        loading = page.locator(selectors['loading_indicator'])
        await loading.wait_for(state="hidden", timeout=10000)
    except Exception:
        # 也可能没有 loading 指示器或已经消失
        pass
    await asyncio.sleep(0.3)


def _parse_modification_scope(scope_str: str) -> List[str]:
    """解析修改范围字符串为路径列表。"""
    if not scope_str or not scope_str.strip():
        return []
    # 支持逗号或分号分隔
    items = scope_str.replace(';', ',').split(',')
    return [item.strip() for item in items if item.strip()]


# ============================================================
# 主入口
# ============================================================

def main():
    args = parse_args()

    # 加载选择器配置（如果提供了自定义配置文件）
    selectors = dict(PAGE_SELECTORS)
    if args.selectors_config:
        try:
            with open(args.selectors_config, 'r', encoding='utf-8') as f:
                custom_selectors = json.load(f)
                selectors.update(custom_selectors)
        except Exception as e:
            print(f"警告: 无法加载选择器配置 {args.selectors_config}: {e}")

    # 执行浏览器自动化
    result = asyncio.run(run_browser_automation(args, selectors))

    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {args.output}")

    # 始终输出 JSON 到 stdout（供调用方解析）
    print("\n--- RESULT_JSON ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 退出码
    if not result["success"]:
        sys.exit(1)


if __name__ == '__main__':
    main()
