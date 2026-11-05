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
 *   { id, title, serverTitle, mineTitle, serverNode, mineNode, action }
 */

function nodeKey(id) {
  // 新节点 id 可能是字符串临时 id（n_xxx）或 null，统一映射
  return id == null ? null : String(id)
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

  /**
   * 合并单个节点的字段（不含 children），返回 { node, conflict }。
   * 前提：该节点在 base/server/mine 三边中至少存在，且不是「仅一边存在」的增删情况
   * （增删在 mergeNode 的存在性分支里已处理）。
   */
  function mergeNodeContent(b, s, m, key) {
    const title = (m && m.title) || (s && s.title) || (b && b.title) || ''
    const node = cloneNode(s || m || b || { title })
    node.id = (m && m.id != null) ? m.id : ((s && s.id != null) ? s.id : (b && b.id != null ? b.id : null))

    // 只有 server 存在（A 新增）或只有 mine 存在（B 新增）时，不存在「两边都改」的冲突
    if (!s || !m) {
      node.title = title
      node.node_type = (m && m.node_type) || (s && s.node_type) || 'case'
      node.is_smoke = !!(m ? m.is_smoke : s.is_smoke)
      node.exec_result = (m ? m.exec_result : s.exec_result) || ''
      node.collapsed = !!(m ? m.collapsed : s.collapsed)
      node.image = (m ? m.image : s.image) || ''
      return { node, conflict: null }
    }

    // b 可能为 undefined：当该节点是双方都「新增」的同 id 节点（理论上不会发生，
    // 因为 id 全局唯一；但 null id 新节点可能出现，此时 b 无，直接保留 mine）。
    if (!b) {
      node.title = m.title || s.title || ''
      node.node_type = m.node_type || 'case'
      node.is_smoke = !!m.is_smoke
      node.exec_result = m.exec_result || ''
      node.collapsed = !!m.collapsed
      node.image = m.image || ''
      return { node, conflict: null }
    }

    const serverChanged = !fieldsEqual(b, s)
    const mineChanged = !fieldsEqual(b, m)
    const serverMineSame = fieldsEqual(s, m)

    if (!serverChanged && !mineChanged) {
      node.title = s.title || ''
      node.node_type = s.node_type || 'case'
      node.is_smoke = !!s.is_smoke
      node.exec_result = s.exec_result || ''
      node.collapsed = !!s.collapsed
      node.image = s.image || ''
      return { node, conflict: null }
    }
    if (serverChanged && !mineChanged) {
      node.title = s.title || ''
      node.node_type = s.node_type || 'case'
      node.is_smoke = !!s.is_smoke
      node.exec_result = s.exec_result || ''
      node.collapsed = !!s.collapsed
      node.image = s.image || ''
      return { node, conflict: null }
    }
    if (!serverChanged && mineChanged) {
      node.title = m.title || ''
      node.node_type = m.node_type || 'case'
      node.is_smoke = !!m.is_smoke
      node.exec_result = m.exec_result || ''
      node.collapsed = !!m.collapsed
      node.image = m.image || ''
      return { node, conflict: null }
    }

    // 两边都改了且内容不同 → 冲突
    if (serverMineSame) {
      node.title = s.title || ''
      node.node_type = s.node_type || 'case'
      node.is_smoke = !!s.is_smoke
      node.exec_result = s.exec_result || ''
      node.collapsed = !!s.collapsed
      node.image = s.image || ''
      return { node, conflict: null }
    }

    const conflict = {
      id: key,
      title: (b && b.title) || (m && m.title) || (s && s.title) || '',
      serverTitle: (s && s.title) || '',
      mineTitle: (m && m.title) || '',
      serverNode: cloneNode(s),
      mineNode: cloneNode(m),
      action: 'edit',
    }
    // 默认保留 mine（B 的），用户可在冲突列表调整
    node.title = m.title || ''
    node.node_type = m.node_type || 'case'
    node.is_smoke = !!m.is_smoke
    node.exec_result = m.exec_result || ''
    node.collapsed = !!m.collapsed
    node.image = m.image || ''
    return { node, conflict }
  }

  /**
   * 判断节点 id 是否为「数据库数字 id」（含数字字符串）。
   * 非数字（null / 临时 id n_xxx）视为「新节点」，合并时独立保留、不按 id 匹配。
   */
  function isNumericId(id) {
    if (id == null) return false
    return /^\d+$/.test(String(id))
  }

  /**
   * 合并子节点列表（按父节点上下文，避免跨父节点串位）。
   * 返回合并后的子节点数组。
   *
   * 关键：数字 id 节点按 id 精确匹配；非数字 id（null）的新节点各自独立保留，
   * 绝不放进 Map 用 null 作 key（否则同父节点下多个新节点会互相覆盖丢失）。
   */
  function mergeChildrenList(baseChildren, serverChildren, mineChildren) {
    const bList = baseChildren || []
    const sList = serverChildren || []
    const mList = mineChildren || []
    const merged = []

    // 数字 id 节点按 id 建索引（只索引数据库已有节点）
    const bById = new Map()
    bList.forEach((c) => { if (isNumericId(c.id)) bById.set(nodeKey(c.id), c) })
    const sById = new Map()
    sList.forEach((c) => { if (isNumericId(c.id)) sById.set(nodeKey(c.id), c) })
    const mById = new Map()
    mList.forEach((c) => { if (isNumericId(c.id)) mById.set(nodeKey(c.id), c) })

    // 新节点（null 或临时 id）按出现顺序收集，独立合并
    const sNew = sList.filter((c) => !isNumericId(c.id))
    const mNew = mList.filter((c) => !isNumericId(c.id))

    // 1) 先合并「数字 id」节点（按 id 匹配，含 base 三态判断）
    const allNumericKeys = new Set([...bById.keys(), ...sById.keys(), ...mById.keys()])
    const handled = new Set()
    for (const key of allNumericKeys) {
      if (handled.has(key)) continue
      const b = bById.get(key)
      const s = sById.get(key)
      const m = mById.get(key)
      const child = mergeNode(b, s, m, key)
      if (child) merged.push(child)
      handled.add(key)
    }

    // 2) 再合并「新节点」：server 的新节点（A 新增）与 mine 的新节点（B 新增）
    //    各自独立保留，不互相配对、不串位。
    for (const sNode of sNew) {
      const child = mergeNode(undefined, sNode, undefined, nodeKey(sNode.id))
      if (child) merged.push(child)
    }
    for (const mNode of mNew) {
      const child = mergeNode(undefined, undefined, mNode, nodeKey(mNode.id))
      if (child) merged.push(child)
    }

    return merged
  }

  /**
   * 合并单个节点（含存在性判断 + 字段合并 + 子节点递归）。
   * 返回合并后的节点（可含 children），或 null（该节点应被删除）。
   */
  function mergeNode(b, s, m, key) {
    // 三边都不存在 → 删除
    if (!s && !m) return null

    // server 无、mine 有
    if (!s && m) {
      if (b) {
        // base 有 → 该节点被 A 删除，B 侧还有
        if (fieldsEqual(b, m)) {
          // B 没改该节点 → 尊重 A 的删除
          return null
        }
        // A 删除了、B 又改了 → 冲突（默认保留 mine，让用户决定）
        conflicts.push({
          id: key,
          title: (m && m.title) || (b && b.title) || '',
          serverTitle: '(已删除)',
          mineTitle: (m && m.title) || '',
          serverNode: null,
          mineNode: cloneNode(m),
          action: 'delete',
        })
        const out = cloneNode(m)
        out.children = mergeChildrenList([], [], m.children)
        return out
      }
      // base 无 → B 新增 → 保留 mine
      const out = cloneNode(m)
      out.children = mergeChildrenList([], [], m.children)
      return out
    }

    // server 有、mine 无
    if (s && !m) {
      if (b) {
        // base 有 → 该节点被 B 删除，A 侧还有
        if (fieldsEqual(b, s)) {
          // A 没改该节点 → 尊重 B 的删除
          return null
        }
        // B 删除了、A 又改了 → 冲突（默认保留 mine=删除，让用户决定）
        conflicts.push({
          id: key,
          title: (b && b.title) || (s && s.title) || '',
          serverTitle: (s && s.title) || '',
          mineTitle: '(已删除)',
          serverNode: cloneNode(s),
          mineNode: null,
          action: 'delete',
        })
        return null
      }
      // base 无 → A 新增 → 保留 server
      const out = cloneNode(s)
      out.children = mergeChildrenList([], s.children, [])
      return out
    }

    // 两边都有 → 合并字段 + 递归子节点
    const { node, conflict } = mergeNodeContent(b, s, m, key)
    if (conflict) conflicts.push(conflict)
    node.children = mergeChildrenList(b ? b.children : [], s.children, m.children)
    return node
  }

  // 根节点：三边根节点视为同一节点（id 可能都为 null），直接合并
  const rootKey = nodeKey(mine.id != null ? mine.id : (server.id != null ? server.id : base.id))
  const root = mergeNode(base, server, mine, rootKey)
  const finalRoot = root || cloneNode(server || mine || base || { title: '', children: [] })
  return { mergedTree: finalRoot, conflicts }
}
