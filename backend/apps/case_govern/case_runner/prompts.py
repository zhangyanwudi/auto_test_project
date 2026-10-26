# -*- coding: utf-8 -*-
"""
巡检规范 AI 提示词：负责两件事，共用同一套「动词表 + 句式表」。

1. 生成规范：用户一句话 → 生成「节点规范草稿」（precondition / step / result）
2. 翻译执行：节点内容 → 操作 JSON（action 序列），供 interpreter 执行

保证「AI 生成的规范」与「AI 执行时理解的规则」严格一致。
"""

# ── 动词表：step 节点写法 → action 映射 ──────────────────────────────
# 用户 step 节点里每行以这些动词开头，AI 只做「动词 → action」的确定性映射
ACTION_VERBS = {
    '打开': 'goto',
    '点击': 'click',
    '输入': 'type',
    '填充': 'type',
    '等待': 'wait',
    '截图': 'screenshot',
    '按键': 'press',
}

# ── 句式表：result 节点写法 → 断言映射 ───────────────────────────────
# result 节点（检查点）限定为这几种固定句式，避免歧义
ASSERT_PATTERNS = {
    '包含': 'contains',      # 「页面 包含 线索」 → 断言页面文本包含「线索」
    '有数据': 'has_data',    # 「列表 有数据」 → 断言列表/表格行数 > 0
    '可点击': 'clickable',   # 「按钮 导出 可点击」 → 断言元素存在且可点
    '存在': 'exists',        # 「元素 xxx 存在」 → 断言元素存在
}


def build_explore_system_prompt():
    """「生成巡检规范」时发给 AI 的 system prompt。

    让 AI 把用户的自然语言描述，转成结构化的节点规范草稿（precondition/step/result）。
    """
    return """你是一个网页自动化巡检助手。用户会用自然语言描述要巡检的页面和功能，你要把它转成一份「节点规范草稿」。

## 输出格式（严格按此结构，用 Markdown 代码块包裹，不要输出代码，只输出规范文本）

```markdown
## 巡检规范草稿

【precondition】
<页面完整地址，如 https://marketing-test.youxi123.com/leadhub/leads>

【step】
<每行一个动作，用固定动词开头>

【result】
<每行一个检查点，用固定句式>
```

## step 动词规范（每行只能用这些动词开头）

- 打开 <网址>                       → 访问页面
- 点击 <按钮/元素文字>              → 点击某个按钮或元素
- 输入 <元素> 为 <内容>             → 在输入框填入内容
- 等待 <元素 或 N秒>                → 等待元素出现或等待固定时长

## result 检查点规范（每行只能用这些句式）

- 页面 包含 <文字>                  → 验证页面上出现了这段文字
- 列表 有数据                       → 验证列表/表格加载出了数据
- 按钮 <文字> 可点击                → 验证按钮存在且可点击
- 元素 <描述> 存在                  → 验证某个元素存在

## 要求

1. 只输出规范文本，不要解释、不要额外说明。
2. step 每一步只做一个动作，动词必须是上面列出的几种。
3. result 每行只写一个检查点。
4. 如果用户描述里有完整 URL，直接填入 precondition；只有域名时，用域名拼出最可能的页面路径并在草稿里标注「请确认路径」。
5. 用户没提到登录/账号时，不要自作主张添加登录步骤。
"""


def build_translate_prompt():
    """「翻译执行」时发给 AI 的 prompt（把节点规范翻译成操作 JSON）。"""
    return """你是网页自动化执行器。根据下面的「节点规范」，生成操作指令 JSON。

## 可用动作（action）

- goto(url)         打开页面（注意：网址放在 url 字段，不是 selector）
- click(selector)   点击
- type(selector, text)  输入（先清空再填）
- wait(selector 或 ms)  等待
- assert(selector, mode)  断言，mode 为 contains/has_data/clickable/exists

## selector 规则

- 有 id 用 id；有 name 用 name；按钮/链接用文字 text=xxx；否则用 css 描述
- **输入框（type 动作）**：用户描述的是「筛选条件字段名」（如「达人昵称」「对方主体」），
  这类输入框的 placeholder 常是「请输入」等通用文案、不唯一，**不要用 placeholder 定位**，
  直接把字段名原文作为 selector（如 `达人昵称`），执行器会按表单项 label 关联到对应输入框
- 断言「页面 包含 X」→ selector 用 body，mode=contains，text=X
- 断言「列表 有数据」→ selector 用列表容器（如 table、.list 或 [class*=list]），mode=has_data
- 断言「元素 X 存在」→ selector 用元素的 css/id（如 #kw、input[type=text]），mode=exists；
  若 X 是字段名（如「达人昵称」），直接用字段名原文即可

## 输出格式（严格）

goto 步骤用 url 字段，其余步骤用 selector 字段。只输出 JSON，不要任何解释：

{"steps":[{"action":"goto","url":"https://xxx"},{"action":"assert","selector":"#kw","mode":"exists"}]}
"""
