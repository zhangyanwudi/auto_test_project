// 回归测试：思维导图保存后的 id 同步与自冲突识别（防止自动保存 / 响应丢失导致节点重复）
// 运行：cd frontend && node --test tests/
import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  mergeTrees,
  treeContentEqual,
  collectNodes,
  applyServerIds,
} from '../src/views/case_govern/mergeUtils.js'

const node = (id, title, children = []) => ({
  id, title, node_type: 'case', is_smoke: false, exec_result: '', collapsed: false, image: '', children,
})

test('自冲突：服务端已落库的内容与本地一致时视为相同，且能回写服务端 id', () => {
  // 本地 mine：A 是刚加的临时节点 n_7；服务端：A 已被上一次（响应丢失的）保存落库为 101
  const mine = node(1, '根', [node('n_7', 'A')])
  const server = node(1, '根', [node(101, 'A')])
  assert.equal(treeContentEqual(mine, server), true)

  const liveNodes = collectNodes(mine)
  applyServerIds(liveNodes, collectNodes(server))
  assert.equal(mine.children[0].id, 101)
})

test('自冲突场景若走三方合并会重复（对照：说明为什么需要自冲突分支）', () => {
  const base = node(1, '根', [])
  const server = node(1, '根', [node(101, 'A')])
  const mine = node(1, '根', [node('n_7', 'A')])
  const { mergedTree } = mergeTrees(base, server, mine)
  assert.equal(mergedTree.children.length, 2)
})

test('保存成功后：内容一致则回写服务端分配的 id', () => {
  const sent = node(1, '根', [node(null, '新节点')])
  const live = node('1', '根', [node('n_9', '新节点')])
  const serverTree = node(1, '根', [node(202, '新节点')])
  assert.equal(treeContentEqual(sent, serverTree), true)

  applyServerIds(collectNodes(live), collectNodes(serverTree))
  assert.equal(live.children[0].id, 202)
})

test('保存期间用户又改了本地标题：仍能按提交快照回写 id，且内容比较基于提交快照', () => {
  const sent = node(1, '根', [node(null, 'A')])
  const serverTree = node(1, '根', [node(303, 'A')])
  // 提交后用户把本地节点改名为 B（live 与 sent 已不一致）
  const live = node(1, '根', [node('n_5', 'B')])
  assert.equal(treeContentEqual(sent, serverTree), true)
  assert.equal(treeContentEqual(sent, live), false)

  applyServerIds(collectNodes(live), collectNodes(serverTree))
  assert.equal(live.children[0].id, 303)
  assert.equal(live.children[0].title, 'B')
})

test('服务端内容与提交内容不一致时不视为相同（不回写，走原有合并）', () => {
  const sent = node(1, '根', [node(null, 'A')])
  const serverTree = node(1, '根', [node(303, 'A'), node(304, '别人加的')])
  assert.equal(treeContentEqual(sent, serverTree), false)
})

test('空标题节点服务端归一为「未命名」时仍视为一致', () => {
  const sent = node(1, '根', [node(null, '')])
  const serverTree = node(1, '根', [node(404, '未命名')])
  assert.equal(treeContentEqual(sent, serverTree), true)
})

test('树结构不同（子节点数量不同）不相等', () => {
  const a = node(1, '根', [node(null, 'A')])
  const b = node(1, '根', [])
  assert.equal(treeContentEqual(a, b), false)
})
