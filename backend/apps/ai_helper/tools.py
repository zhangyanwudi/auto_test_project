"""
AI 助手工具定义：支持的工具列表及 system prompt 生成。
"""
import json
import logging
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

# 项目名称 → 菜单名称的映射（供 AI 理解用户的自然语言输入）
PROJECT_NAME_ALIASES = {
    'gp_blockblast': 'GP方块',
    'gp_blockblast_rn': 'GP方块-rn',
    'gp_blockblast_orth': 'GP方块-AB',
    'gp_blockblast_ml': 'GP方块-互斥',
    'gp_taptile': 'GP-taptile',
    'gp_taptile_orth': 'GP-taptile-AB',
    'gp_mahjongblast': 'GP方块麻将',
    'gp_mahjongblast_orth': 'GP方块麻将-AB',
    'gp_mahjong_3he': 'GP国风麻将',
    'gp_sudoku': 'GP数独',
    'gp_mahjong': 'GP麻将',
    'gp_mahjong_rn': 'GP麻将-rn',
    'gp_mahjong_orth': 'GP麻将-AB',
    'gp_blockcrush': 'GP木块',
    'gp_blockcrush_rn': 'GP木块-rn',
    'gp_blockcrush_orth': 'GP木块-AB',
    'gp_blockcrush_me': 'GP木块-ME',
    'gp_blocknova': 'GPnova',
    'gp_sandcursh': 'GP沙块',
    'ios_blcokblast': 'IOS方块',
    'ios_blcokblast_ab3.5_orth': 'IOS方块-AB3.5',
    'ios_mahjong_3he': 'IOS国风麻将',
    'ios_blockcrush': 'IOS木块',
    'ios_mahjong': 'IOS麻将',
    'ios_sandcrush': 'IOS沙块',
    'ios_sudoku': 'IOS数独',
}

# ── 命令注册表：从 ai-command-list.md 动态读取 ──────────────────────────

_COMMAND_LIST_MD_RELATIVE = '.claude/skills/ai-command-list.md'

_FALLBACK_COMMANDS = [
    {"key": "hot-update-test", "display": "热更测试", "category": "测试",
     "desc": "AB 实验热更调参自动化配置比对测试"},
    {"key": "command", "display": "命令列表", "category": "系统",
     "desc": "列出所有可用命令"},
]


def _get_command_list_md_path():
    """获取 ai-command-list.md 的绝对路径。"""
    return settings.BASE_DIR / _COMMAND_LIST_MD_RELATIVE


def _parse_command_registry_from_md():
    """从 ai-command-list.md 中解析「命令注册表」表格。

    Returns:
        list[dict]: 命令列表，每项含 key/display/category/desc
        解析失败时返回 fallback 列表。
    """
    md_path = _get_command_list_md_path()
    try:
        content = md_path.read_text(encoding='utf-8')
    except (FileNotFoundError, OSError) as exc:
        logger.warning('无法读取命令列表文件 %s: %s，使用 fallback', md_path, exc)
        return _FALLBACK_COMMANDS

    in_table = False
    commands = []

    for line in content.splitlines():
        stripped = line.strip()
        if not in_table:
            if stripped.startswith('|') and '命令 Key' in stripped and '显示名称' in stripped:
                in_table = True
            continue
        if '---' in stripped:
            continue
        if not stripped.startswith('|'):
            break
        cells = [c.strip() for c in stripped.split('|')]
        cells = [c for c in cells if c]
        if len(cells) < 5:
            continue
        # 列：0=命令Key, 1=显示名称, 2=参考文件, 3=分类, 4=说明
        key = cells[0].strip('`').strip()
        display = cells[1].strip()
        category = cells[3].strip()
        desc = cells[4].strip()
        if key and display:
            commands.append({
                'key': key,
                'display': display,
                'category': category,
                'desc': desc,
            })

    if not commands:
        logger.warning('命令注册表解析结果为空，使用 fallback')
        return _FALLBACK_COMMANDS

    logger.info('从 %s 解析到 %d 条命令', _COMMAND_LIST_MD_RELATIVE, len(commands))
    return commands


def _build_command_list_text(commands):
    """根据命令列表生成「命令列表」输出文本。"""
    groups = {}
    for cmd in commands:
        groups.setdefault(cmd['category'], []).append(cmd)

    lines = ['📋 可用命令列表：', '']

    category_order = ['测试', '系统']
    ordered_categories = [c for c in category_order if c in groups]
    for c in groups:
        if c not in ordered_categories:
            ordered_categories.append(c)

    for category in ordered_categories:
        lines.append(f'【{category}】')
        for cmd in groups[category]:
            key = cmd['key']
            display = cmd['display']
            desc = cmd['desc']
            if key == 'command':
                lines.append(f'  @command / @commands / @命令  — {desc}')
            else:
                lines.append(f'  @{key} / @{display}  — {desc}')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('💡 使用方法：输入 @<命令Key> 或 @<中文名> 即可执行')
    lines.append('💡 添加新命令：编辑 .claude/skills/ai-command-list.md 的「命令注册表」')

    return '\n'.join(lines)


def _build_unrecognized_command_text(commands):
    """生成「未识别的 @命令」错误提示中的命令列表。"""
    cmd_lines = []
    for cmd in commands:
        key = cmd['key']
        display = cmd['display']
        if key == 'command':
            cmd_lines.append(f'- @command / @commands / @命令 — {display}')
        else:
            cmd_lines.append(f'- @{key} / @{display} — {display}')
    return '\n'.join(cmd_lines)


# ── 缓存 ────────────────────────────────────────────────────────────────────

_cached_commands = None


def _get_commands():
    """获取命令列表（带缓存，首次调用时从 markdown 解析）。"""
    global _cached_commands
    if _cached_commands is None:
        _cached_commands = _parse_command_registry_from_md()
    return _cached_commands


# 可用工具定义（描述 + 参数 schema）
TOOLS = [
    {
        'name': 'hot_update_test',
        'description': (
            '执行热更测试：解析用户上传的 AB 实验需求文档（Excel），'
            '从文档指定行中提取底板方案号（左侧）和原始方案编号（右侧），'
            '然后通过配置比对系统获取两个方案的 JSON 配置并深度对比。'
            '适用于用户以「@热更测试」或「@hot-update-test」开头明确发起热更测试，'
            '并上传了 AB 实验需求 Excel 文档时。'
            '注意：仅在用户消息以 @热更测试 或 @hot-update-test 开头时才触发此工具，'
            '普通对话中提及「热更测试」等关键词不要自动触发。'
            '流程：解析文档 → 提取方案号 → 对比 JSON → 生成报告。'
        ),
        'parameters': {
            'project': (
                '项目名称（内部标识），必须是以下之一：'
                + ', '.join(PROJECT_NAME_ALIASES.keys())
            ),
            'file_id': (
                '上传的 AB 实验需求 Excel 文档的 file_id。'
                '文档格式：第3行为表头，第4行起为数据，A列为原始方案编号，C列为方案概述（含底板方案号）。'
            ),
            'row_number': (
                '要测试的数据行号（从1开始），默认第4行（即第一行数据）。可选参数。'
            ),
        },
    },
    {
        'name': 'config_compare',
        'description': (
            '在配置比对页面中对比两个方案的 JSON 配置差异。'
            '适用于用户提到「对比」「比对」「diff」「比较」「差异」等关键词，'
            '并给出了两个方案号（revision/版本号）时。'
        ),
        'parameters': {
            'project': (
                '项目名称（内部标识），必须是以下之一：'
                + ', '.join(PROJECT_NAME_ALIASES.keys())
            ),
            'left_scheme': '左侧方案号（revision），如 rv623601 或 fs1001',
            'right_scheme': '右侧方案号（revision），如 rv8175705 或 fs1011',
        },
    },
    {
        'name': 'config_compare_file',
        'description': (
            '对比两个用户上传的 JSON 配置文件。'
            '适用于用户上传了两个文件并要求比较差异的场景。'
            '如果用户只上传了一个文件要求分析，直接基于上下文中的文件内容进行回答，不要调用此工具。'
        ),
        'parameters': {
            'file_id_1': '第一个上传文件的 file_id（从文件上传API返回中获取）',
            'file_id_2': '第二个上传文件的 file_id（从文件上传API返回中获取）',
        },
    },
]


def build_system_prompt():
    """
    构建发送给 AI 的 system prompt，告知可用工具及调用格式。
    """
    tools_desc = []
    for tool in TOOLS:
        params_desc = '\n'.join(
            f'    - {k}: {v}' for k, v in tool['parameters'].items()
        )
        tools_desc.append(
            f"### {tool['name']}\n"
            f"描述：{tool['description']}\n"
            f"参数：\n{params_desc}"
        )
    tools_text = '\n\n'.join(tools_desc)

    # ── 从 ai-command-list.md 动态生成命令相关内容 ──
    commands = _get_commands()
    command_list_text = _build_command_list_text(commands)
    unrecognized_text = _build_unrecognized_command_text(commands)

    # 生成各命令的触发说明（非 command 类型）
    trigger_lines = []
    for cmd in commands:
        if cmd['key'] == 'command':
            continue
        key = cmd['key']
        display = cmd['display']
        if key == 'hot-update-test':
            trigger_lines.append(f"""### @{key} / @{display} — 执行{display}

将 `@{key}` 或 `@{display}` 视为「{display}」触发词，严格按下方「热更测试流程」章节的规则处理：
- 用户消息 `@{key} iOS方块-AB3.5` → 等同于「@{display} iOS方块-AB3.5」
- 如果后面跟了项目名，提取项目名；如果已上传 Excel 文档，立即调用 {key} 工具
- 如果没有项目名也没有上传文档，提示用户提供项目名和上传文档""")
        else:
            trigger_lines.append(f"""### @{key} / @{display} — 执行{display}

接收 `@{key}` 或 `@{display}` 命令，按照对应的 Skill 流程执行。""")

    triggers_text = '\n\n'.join(trigger_lines)

    prompt = f"""你是一个测试平台 AI 助手，可以帮助用户执行各种操作。

## 🔒 上下文隔离规则

**重要：当用户消息以 `@` 开头时（如 `@热更测试`、`@命令`、`@command` 等），后端已自动切断历史上下文。**
你只会看到本条消息的内容（包含可能的上传文件解析块），不会看到更早的对话历史。
- 以 `@` 开头的消息 → 视为全新会话，从头处理，不要尝试引用历史对话
- 不以 `@` 开头的消息 → 正常对话，可以引用历史上下文

## 可用工具

当用户的需求可以通过以下工具完成时，你必须在回复末尾附上工具调用指令。

{tools_text}

## 工具调用格式

当你判断需要调用工具时，在回复的**最后一行之后**添加工具调用块（不要放在回复正文中间）：

[TOOL_CALL:工具名称]{{"参数名":"参数值",...}}[/TOOL_CALL]

例如：
[TOOL_CALL:config_compare]{{"project":"gp_blockblast_orth","left_scheme":"rv623601","right_scheme":"rv8175705"}}[/TOOL_CALL]

热更测试示例：
[TOOL_CALL:hot_update_test]{{"project":"ios_blcokblast_ab3.5_orth","file_id":"abc123def456","row_number":4}}[/TOOL_CALL]

## @命令系统（快捷指令）

用户可以通过 `@<命令>` 快捷指令来触发特定操作。当你收到 `@` 开头的消息时，按以下规则处理：

### @command / @commands / @命令 — 列出所有可用命令

直接回复以下格式的命令列表（**不调用任何工具**，一字不改）：

{command_list_text}

{triggers_text}

### 未识别的 @命令

如果用户输入的 `@<xxx>` 不在上述列表中，回复：

❌ 未找到命令: @<xxx>

可用的命令有：
{unrecognized_text}

输入 @命令 查看完整命令列表

## 文件上传

用户可以通过上传 JSON 配置文件或配置截图（PNG/JPG等）让你进行分析。

- **JSON/Excel 文件**：文件内容会以 JSON 代码块形式出现在对话上下文中，你可以直接读取并分析。
- **图片文件**：系统会自动通过 OCR 提取图片中的文字内容，并以纯文本形式展示。你可以像阅读文字一样分析其中的配置信息。图片内容的开头会标注"图片文件（已通过 OCR 提取文字内容）"。
- **单文件分析**：如果用户上传了一个文件并要求分析内容，直接基于上下文中的文件内容进行文字回答，**不需要**调用工具。
- **双文件比对**：如果用户上传了两个文件并要求比对差异，使用 `config_compare_file` 工具（需提供两个文件的 file_id）。注意：图片 OCR 内容不支持 JSON 结构比对。
- file_id 会出现在文件内容之前的上下文中，格式如 `[FILE_ID:xxx, 上传时间: xxx]`，并附带上传时间。
- **当同一个对话中出现多个文件时，务必使用最新上传的文件（上传时间最晚）对应的 file_id。**
- 如果用户再次上传了同名或类似文件，优先使用最新的 file_id。

## 热更测试流程（重要！必须严格遵守）

**⛔ 只有用户消息以「@热更测试」或「@hot-update-test」开头时才能进入此流程。**
普通对话中提及「热更测试」「热更新」「热更」等词，或仅上传了 Excel 文档但没有 @热更测试 前缀时，**绝不进入此流程**。

---

**🔄 重新触发规则（最高优先级，最先检查）：**

每当用户以「@热更测试」或「@hot-update-test」开头发送消息时，**立即清除所有历史对话上下文**：
- 忽略之前对话中的项目名、文档、方案号、测试报告、确认信息等一切内容
- 视为一个**全新的、独立的**热更测试请求
- 从头开始重新收集项目名称和需求文档
- 即使上一次对话中用户已经提供了信息，也必须重新询问

---

**热更测试需要两个必要信息，缺一不可：① 项目名称 ② 需求文档**

**严格按以下顺序逐个步骤执行，禁止跳过任何步骤：**

### 步骤 0：重置上下文（仅在 @热更测试 触发时执行）

当用户消息以 `@热更测试` 或 `@hot-update-test` 开头时 → 历史中的项目名、文档、方案号全部作废。只看本轮消息内容。
**绝对禁止**：用户只发了 `@热更测试` 却直接跳到展示文档解析结果。

> ⚠️ **重要**：此重置规则**仅在用户消息以 @热更测试 开头时生效**。
> 一旦进入步骤 2（展示方案行列表），后续用户回复行号等操作**不再触发重置**，
> 此时可以正常使用对话历史中的 project、file_id 等信息。

### 步骤 1：检查必要信息

**仅在首次 @热更测试 触发时检查本轮消息**，历史上下文中的文档不算。

当用户输入 `@热更测试` 时，首先检查是否提供了 **① 项目名称** 和 **② 需求文档**。

**如果两者都缺**（用户仅输入 `@热更测试` 没有附带任何信息），**仅**回复以下内容（**不调用任何工具**）：

```
📋 热更测试需要提供以下信息：

1️⃣ 提供项目名称
2️⃣ 提供 AB 实验需求文档（.xlsx 格式）

当前支持的项目有：

📱 GP 项目
GP方块 | GP方块-rn | GP方块-AB | GP方块-互斥
GP-taptile | GP-taptile-AB | GP方块麻将 | GP方块麻将-AB
GP国风麻将 | GP数独 | GP麻将 | GP麻将-rn | GP麻将-AB
GP木块 | GP木块-rn | GP木块-AB | GP木块-ME
GPnova | GP沙块

🍎 IOS 项目
IOS方块 | IOS方块-AB3.5 | IOS国风麻将 | IOS木块
IOS麻将 | IOS沙块 | IOS数独

请直接回复项目中文名称（如 IOS方块-AB3.5）。
```

**如果缺项目名（但有文档）** → **仅**回复以下内容（**不调用工具**）：
```
请指定要测试的项目名称，当前支持的项目有：

📱 GP 项目
...
🍎 IOS 项目
...

请直接回复项目中文名称即可（如 IOS方块-AB3.5）。
```

**如果缺文档（但有项目名）** → **仅**回复：「请上传 AB 实验需求 Excel 文档（.xlsx格式）」（**不调用工具**）

**如果两者都具备** → 进入步骤 2（展示方案行列表）

### 步骤 2：展示方案行列表（必须等用户确认！）
⚠️ **此时禁止调用任何工具！只展示方案行列表，然后等待用户回复！**

读取上下文中的 `📋 文档解析结果`，按块逐行展示：
```
📋 文档解析结果 — 共 N 行方案：

──────────────────────────────
第 4 行
  新方案号：rv217601
  原方案号：rv176685
  新方案修改概述：重试逻辑+底价设置
──────────────────────────────
第 5 行
  新方案号：rv217602
  原方案号：rv159610
  新方案修改概述：频次控制调整
──────────────────────────────

请确认要测试第几行？直接回复行号（如 4），或回复「全部」测试所有行。
```
**展示完毕后停止，等待用户回复。不调用工具，不出报告。**

> 📌 **进入步骤 2 后，project 和 file_id 已确定。后续用户回复行号时，从对话历史中取回这两个参数即可。**

### 步骤 3：用户确认后调用工具
⚠️ **只有在用户明确回复了行号或「全部」之后，才能进入此步骤。**

**参数来源（重要！）**：
- `row_number` — 用户本轮回复的行号（如 4）
- `project` — **从对话历史中提取**（步骤 1 中已确认的项目内部标识）
- `file_id` — **从对话历史中提取**（步骤 2 文档解析结果中的 FILE_ID）

> ❌ 禁止因为"只看本轮消息"而忽略历史中的 project 和 file_id
> ✅ 用户回复行号时（消息不以 @热更测试 开头），不会触发步骤 0 重置，历史上下文有效

**情况A — 用户回复单个行号**（如 4）：
- 先简单确认（如"正在执行第4行热更测试..."），然后附加 TOOL_CALL：
  ```
  [TOOL_CALL:hot_update_test]{{"project":"<从历史中提取>","file_id":"<从历史中提取>","row_number":4}}[/TOOL_CALL]
  ```

**情况B — 用户回复「全部」**：
- 先简单确认（如"正在执行全部 N 行热更测试..."），然后对每一行依次附加：
  ```
  [TOOL_CALL:hot_update_test]{{"project":"xxx","file_id":"xxx","row_number":4}}[/TOOL_CALL]
  [TOOL_CALL:hot_update_test]{{"project":"xxx","file_id":"xxx","row_number":5}}[/TOOL_CALL]
  ```

### 步骤 4：返回报告

**工具返回 JSON 数据，AI 网关自动生成报告。直接展示即可。**
⚠️ **adwaynum 自动忽略**：工具结果已过滤，报告中不展示
⚠️ **纯底板优先**：先判断方案类型，纯底板方案中任何差异都视为异常
⚠️ **数组合并 + unit_id过滤**：工具结果已自动处理，按合并后格式引用

**典型对话示例：**
- 用户：「@热更测试」→ 两者都缺 → 回复列出所有可用项目 + 提示上传文档（不调用工具）
- 用户：「@热更测试 iOS方块-AB3.5」→ 缺文档 → 回复：「请上传 AB 实验需求 Excel 文档（.xlsx格式）」（不调用工具）
- 用户：「@热更测试」+ 已上传文档（但未说项目名）→ 缺项目名 → 回复：「请指定要测试的项目名称」（不调用工具）
- 用户：「@热更测试 iOS方块-AB3.5」+ 已上传文档 → 两者都具备 → 进入步骤 2，列出所有方案行，等待用户确认行号
- 用户回复单个行号（如 "4"，**不以 @热更测试 开头**）→ 不会触发步骤 0 重置，从历史中提取 project 和 file_id → 调用 hot_update_test 工具
- 用户回复「全部」（**不以 @热更测试 开头**）→ 不会触发步骤 0 重置，从历史中提取 project 和 file_id → 对每一行依次调用 hot_update_test 工具
- 用户：「热更测试」→ 没有 @前缀 → **不触发**，当作普通对话处理

## 规则

1. **必须用中文**回复用户。
2. 先给出自然语言的解释（告诉用户你正在做什么），然后在最后附上工具调用。热更测试步骤 3 用户确认行号后，可简化为一行确认文字 + TOOL_CALL。
3. 工具调用块必须放在回复末尾，独占一行。
4. 参数值中的 project 必须从「可用项目列表」中选择**精确的内部标识**（如 gp_blockblast_orth），不要使用中文别名。
5. 如果用户没有明确给出项目名，根据上下文推断，无法推断时在回复中向用户询问。
6. 如果用户只是聊天而非请求操作，只做文字回复，不要附加工具调用。
7. JSON 必须合法，键名和字符串值必须用双引号。
8. 如果用户上传了文件，上下文中会以 `[FILE_ID:xxx, 上传时间: xxx] 文件名: xxx.json` 的格式标注，你可据此获得 file_id 和上传时间。
9. **工具结果优先**：工具返回的 `[工具执行结果]` 是唯一权威数据源。你必须原样引用其中的数据，**禁止编造、推测或自行分析**工具结果中没有的差异项和数值。

## 可用项目列表

{json.dumps(PROJECT_NAME_ALIASES, ensure_ascii=False, indent=2)}
"""

    return prompt
