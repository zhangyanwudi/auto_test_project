/**
 * 思维导图节点树三方合并（base / server / mine）。
 *
 * 用于多页签同时编辑同一用例时，B 保存冲突后的自动合并：
 * - base    ：B 加载该用例时的快照
 * - server  ：A 保存后服务器上的最新树（含节点 id）
 * - mine    ：B 当前编辑的树（含节点 id）
 *
 * 合并规则：
 * - 节点字段相同（base==server==mine）→ 无冲突，取 server/mine 均可
 * - 只有 server 改 → 用 server
 * - 只有 mine 改 → 用 mine
 * - server 和 mine 都改，且改得不一样 → 冲突（整节点冲突）
 * - 新增/删除按 id 判断，单向新增/删除不算冲突；双向冲突才记录
 *
 * 返回 { mergedTree, conflicts }，conflicts 元素：
 *   { id, title, serverTitle, mineTitle, serverNode, mineNode }
 */

function nodeKey(id) {
  // 新节点 id 可能是字符串临时 id（n_xxx）或 null，统一映射
  return id == null ? null : String(id)
}

function buildIdMap(tree, map = new Map()) {
  map.set(nodeKey(tree.id), tree)
  for (const ch of tree.children || []) {
    buildIdMap(ch, map)
  }
  return map
}

function fieldsEqual(a, b) {
  return a.title === b.title
    && a.node_type === b.node_type
    && !!a.is_smoke === !!b.is_smoke
    && (a.exec_result || '') === (b.exec_result || '')
    && !!a.collapsed === !!b.collapsed
    && (a.image || '') === (b.image || '')
}

function cloneNode(n) {
  return {
    id: n.id,
    title: n.title || '',
    node_type: n.node_type || 'case',
    is_smoke: !!n.is_smoke,
    exec_result: n.exec_result || '',
    collapsed: !!n.collapsed,
    image: n.image || '',
    children: [],
  }
}

export function mergeTrees(base, server, mine) {
  const conflicts = []
  const baseMap = buildIdMap(base)
  const serverMap = buildIdMap(server)
  const mineMap = buildIdMap(mine)

  // 收集所有节点 id（含新建临时 id）
  const allKeys = new Set([...baseMap.keys(), ...serverMap.keys(), ...mineMap.keys()])

  function mergeNode(id, parentBaseKey, parentServerKey, parentMineKey) {
    const key = id == null ? null : nodeKey(id)
    const b = baseMap.get(key)
    const s = serverMap.get(key)
    const m = mineMap.get(key)

    // 节点只存在于某一边
    if (!s && !m) return null
    if (!s && m) {
      // 只有 mine 有（B 新增）→ 保留 mine
      const out = cloneNode(m)
      for (const ch of m.children || []) {
        const mergedChild = mergeNode(ch.id, key, null, key)
        if (mergedChild) out.children.push(mergedChild)
      }
      return out
    }
    if (s && !m) {
      // 只有 server 有（A 新增，B 没这个节点，但 B 未删除）→ 用 server
      // 注意：若 B 删除了该节点（mine 无），说明 A、B 一边新增一边删除，这里是 server 有 mine 无，
      // 而 base 也可能有/无。若 base 有而 mine 无 → B 删除了，A 没改 → 跟 A 保留？需判断。
      // 简化处理：base 无（A 新增）+ mine 无 → 保留 server；base 有 + mine 无 → B 删除，A 未改则跟随删除，A 改了则冲突。
      const bHas = baseMap.has(key)
      if (!bHas) {
        // A 新增的节点，B 没见过 → 保留 server
        const out = cloneNode(s)
        for (const ch of s.children || []) {
          const mergedChild = mergeNode(ch.id, null, key, null)
          if (mergedChild) out.children.push(mergedChild)
        }
        return out
      }
      // base 有，mine 无 → B 删除了
      if (fieldsEqual(b, s)) {
        // A 没改该节点，跟随 B 删除
        return null
      }
      // A 改了、B 删了 → 冲突
      conflicts.push({
        id: key,
        title: (m && m.title) || (b && b.title) || '',
        serverTitle: (s && s.title) || '',
        mineTitle: '(已删除)',
        serverNode: cloneNode(s),
        mineNode: null,
        action: 'delete',
      })
      // 默认保留 mine（删除），用户在冲突列表可改
      return null
    }

    // 两边都有
    // 关键修复：b（base）可能为 undefined —— B 新增的节点（mine 有、base 无），
    // 此时该节点 A 不可能改过，直接保留 mine（B 的），避免访问 b.title 报错。
    if (!b) {
      const out = cloneNode(m)
      mergeChildren(out, s, m, key)
      return out
    }
    const serverChanged = !fieldsEqual(b, s)
    const mineChanged = !fieldsEqual(b, m)
    const serverMineSame = fieldsEqual(s, m)

    if (!serverChanged && !mineChanged) {
      // 都没改，或改动一致
      const out = cloneNode(s)
      mergeChildren(out, s, m, key)
      return out
    }
    if (serverChanged && !mineChanged) {
      // 只有 A 改 → 用 server
      const out = cloneNode(s)
      mergeChildren(out, s, m, key)
      return out
    }
    if (!serverChanged && mineChanged) {
      // 只有 B 改 → 用 mine
      const out = cloneNode(m)
      mergeChildren(out, s, m, key)
      return out
    }
    // 两边都改了，且内容不同 → 冲突
    if (serverMineSame) {
      // 改成了相同内容（如都改成了同一句话）→ 无冲突
      const out = cloneNode(s)
      mergeChildren(out, s, m, key)
      return out
    }
    conflicts.push({
      id: key,
      title: (b && b.title) || (m && m.title) || (s && s.title) || '',
      serverTitle: (s && s.title) || '',
      mineTitle: (m && m.title) || '',
      serverNode: cloneNode(s),
      mineNode: cloneNode(m),
      action: 'edit',
    })
    // 默认保留 mine（B 的），用户可在冲突列表调整
    const out = cloneNode(m)
    mergeChildren(out, s, m, key)
    return out
  }

  function mergeChildren(outNode, s, m, key) {
    // 子节点顺序：以 server 为基准，附加 mine 中新增的子节点
    const sChildren = (s && s.children) || []
    const mChildren = (m && m.children) || []
    const merged = []
    const sKeys = sChildren.map((c) => nodeKey(c.id))
    const mKeys = mChildren.map((c) => nodeKey(c.id))

    // 先按 server 顺序合并
    for (const sc of sChildren) {
      const mc = mChildren.find((c) => nodeKey(c.id) === nodeKey(sc.id))
      const bc = null
      const mergedChild = mergeNode(sc.id, key, key, key)
      if (mergedChild) merged.push(mergedChild)
    }
    // 再补 mine 中 server 没有的新增子节点
    for (const mc of mChildren) {
      if (!sKeys.includes(nodeKey(mc.id))) {
        const mergedChild = mergeNode(mc.id, key, key, key)
        if (mergedChild) merged.push(mergedChild)
      }
    }
    outNode.children = merged
  }

  const root = mergeNode(mine.id != null ? mine.id : (server.id != null ? server.id : base.id), null, null, null)
  const finalRoot = root || cloneNode(server || mine || base || { title: '', children: [] })
  return { mergedTree: finalRoot, conflicts }
}
