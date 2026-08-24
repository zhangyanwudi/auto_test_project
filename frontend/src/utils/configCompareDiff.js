/**
 * 配置比对：JSON 递归比对与过滤（纯函数，便于单测与复用）
 *
 * @param {object} leftJson 左侧 JSON
 * @param {object} rightJson 右侧 JSON（始终与左侧同一套对象比较，勿交换参数）
 * @param {'left'|'right'} [panel='left'] 当前渲染左栏还是右栏，用于「新增」标在真正有数据的侧
 *
 * 规则：对方无 →「新增」（绿色）；两侧都有但不一致 →「差异」，每栏只显示本侧值。
 */
function spanNew(val) {
  return `<span class="diff-new">+ ${JSON.stringify(val)}</span>`
}

/** 差异：仅本侧值；展示为 差异 + JSON.stringify(值) */
function spanDiffOwnSide(panel, leftVal, rightVal) {
  const v = panel === 'left' ? leftVal : rightVal
  return `<span class="diff-chg"><span class="diff-chg-prefix">差异</span>${JSON.stringify(v)}</span>`
}

export function compareJsonTree(leftJson, rightJson, panel = 'left') {
  if (!leftJson || typeof leftJson !== 'object') leftJson = {}
  if (!rightJson || typeof rightJson !== 'object') rightJson = {}
  const isLeftPanel = panel === 'left'
  const result = {}
  const keys = new Set([...Object.keys(leftJson), ...Object.keys(rightJson)])
  keys.forEach((key) => {
    if (Array.isArray(leftJson[key]) && Array.isArray(rightJson[key])) {
      let isDictArray = false
      if (
        leftJson[key].length > 0 &&
        typeof leftJson[key][0] === 'object' &&
        leftJson[key][0] !== null &&
        !Array.isArray(leftJson[key][0])
      ) {
        isDictArray = true
      }
      if (
        rightJson[key].length > 0 &&
        typeof rightJson[key][0] === 'object' &&
        rightJson[key][0] !== null &&
        !Array.isArray(rightJson[key][0])
      ) {
        isDictArray = true
      }
      if (isDictArray) {
        const maxLength = Math.max(leftJson[key].length, rightJson[key].length)
        const arrayResult = []
        for (let i = 0; i < maxLength; i++) {
          const lItem = leftJson[key][i]
          const rItem = rightJson[key][i]
          if (lItem !== undefined && rItem !== undefined) {
            const diff = compareJsonTree(lItem, rItem, panel)
            arrayResult.push(`索引 ${i}: ${diff}`)
          } else if (lItem !== undefined && rItem === undefined) {
            if (isLeftPanel) {
              arrayResult.push(`索引 ${i}: ${spanNew(lItem)}`)
            } else {
              arrayResult.push(
                `索引 ${i}: <span class="diff-missing">- ${JSON.stringify(lItem)}</span>`
              )
            }
          } else if (lItem === undefined && rItem !== undefined) {
            if (isLeftPanel) {
              arrayResult.push(
                `索引 ${i}: <span class="diff-missing">- ${JSON.stringify(rItem)}</span>`
              )
            } else {
              arrayResult.push(`索引 ${i}: ${spanNew(rItem)}`)
            }
          }
        }
        result[key] = arrayResult.join('<br/>')
      } else {
        const sortedLeft = leftJson[key].slice()
        const sortedRight = rightJson[key].slice()
        if (JSON.stringify(sortedLeft) !== JSON.stringify(sortedRight)) {
          result[key] = spanDiffOwnSide(panel, sortedLeft, sortedRight)
        } else {
          result[key] = `<span class="diff-same">${JSON.stringify(sortedLeft)}</span>`
        }
      }
    } else if (
      typeof leftJson[key] === 'object' &&
      leftJson[key] !== null &&
      typeof rightJson[key] === 'object' &&
      rightJson[key] !== null
    ) {
      const subResult = compareJsonTree(leftJson[key], rightJson[key], panel)
      if (subResult) result[key] = subResult
    } else if (leftJson[key] !== rightJson[key]) {
      if (leftJson[key] === undefined && rightJson[key] !== undefined) {
        if (isLeftPanel) {
          result[key] = `<span class="diff-missing">- ${JSON.stringify(rightJson[key])}</span>`
        } else {
          result[key] = spanNew(rightJson[key])
        }
      } else if (rightJson[key] === undefined && leftJson[key] !== undefined) {
        if (isLeftPanel) {
          result[key] = spanNew(leftJson[key])
        } else {
          result[key] = `<span class="diff-missing">- ${JSON.stringify(leftJson[key])}</span>`
        }
      } else {
        result[key] = spanDiffOwnSide(panel, leftJson[key], rightJson[key])
      }
    } else {
      result[key] = `<span class="diff-same">${JSON.stringify(leftJson[key])}</span>`
    }
  })
  return Object.entries(result)
    .map(([key, value]) => `${key}: ${value}`)
    .join('<br/>')
}

/**
 * 规范化两侧 VIEW DATA 的键，去除各自的 region 前缀，使得跨 ab_config 的单元可以按同名 key 匹配。
 * 例如 leftData {"ab_config_01.ad_unit_1": v1}、rightData {"ab_config_02.ad_unit_1": v2}
 * → leftNorm {"ad_unit_1": v1}、rightNorm {"ad_unit_1": v2}
 */
export function normalizeCrossConfigViewData(leftData, rightData, leftRegion, rightRegion) {
  const leftNorm = {}
  const rightNorm = {}
  const leftPrefix = leftRegion ? leftRegion + '.' : ''
  const rightPrefix = rightRegion ? rightRegion + '.' : ''

  for (const [key, value] of Object.entries(leftData || {})) {
    const suffix = leftPrefix && key.startsWith(leftPrefix) ? key.slice(leftPrefix.length) : key
    leftNorm[suffix] = value
  }
  for (const [key, value] of Object.entries(rightData || {})) {
    const suffix = rightPrefix && key.startsWith(rightPrefix) ? key.slice(rightPrefix.length) : key
    rightNorm[suffix] = value
  }

  return { leftNorm, rightNorm }
}

const TEXT_DIFF_LINE_RE = /(diff-chg|diff-new|diff-missing|diff-add|差异:|未提取到)/
const TEXT_BANNER_RE = /=============/
/** 区域分隔行：=============key============= */
const TEXT_BANNER_KEY_RE = /={3,}([^=]+?)={3,}/
/** 文本样式成对对齐时的占位行（需被 wrapTextAsStructuredHtml 保留） */
export const TEXT_DIFF_BLANK_LINE = '<span class="diff-blank">&nbsp;</span>'

function splitTextHtmlLines(input_data) {
  return (typeof input_data === 'string' ? input_data.split('<br/>') : input_data || [])
    .map((line) => (typeof line === 'string' ? line.trim() : ''))
    .filter((line) => line.length > 0)
}

function isTextDiffLine(line) {
  return TEXT_DIFF_LINE_RE.test(line)
}

function parseTextBannerKey(line) {
  const m = String(line || '').match(TEXT_BANNER_KEY_RE)
  return m ? m[1].trim() : ''
}

/**
 * 按 =============key============= 切成有序分段，便于左右按 key 对齐。
 * @returns {{ preface: string[], sections: Array<{ key: string, banner: string, lines: string[] }> }}
 */
export function splitTextHtmlByBanners(input_data) {
  const lines = splitTextHtmlLines(input_data)
  const preface = []
  const sections = []
  let current = null
  for (const line of lines) {
    const key = parseTextBannerKey(line)
    if (key && TEXT_BANNER_RE.test(line)) {
      current = { key, banner: line, lines: [] }
      sections.push(current)
      continue
    }
    if (current) current.lines.push(line)
    else preface.push(line)
  }
  return { preface, sections }
}

function filterTextLinesKeepDiff(lines) {
  return (lines || []).filter((line) => isTextDiffLine(line) || TEXT_BANNER_RE.test(line))
}

function padTextLinesToLength(lines, targetLen) {
  const out = [...(lines || [])]
  while (out.length < targetLen) out.push(TEXT_DIFF_BLANK_LINE)
  return out
}

export function filterDiffData(input_data) {
  const lines = splitTextHtmlLines(input_data)

  // 第一轮：标记每行是否应保留（差异内容或分隔符行）
  const keep = lines.map((line) => isTextDiffLine(line) || TEXT_BANNER_RE.test(line))

  // 第二轮：清理孤儿分隔符——分隔符后直到下一个分隔符或行尾，若无差异内容则移除
  let pendingBannerIdx = -1
  for (let i = 0; i < lines.length; i++) {
    if (TEXT_BANNER_RE.test(lines[i])) {
      // 检查上一个待定分隔符是否有差异内容跟随
      if (pendingBannerIdx >= 0) {
        let hasContent = false
        for (let j = pendingBannerIdx + 1; j < i; j++) {
          if (keep[j] && !TEXT_BANNER_RE.test(lines[j])) {
            hasContent = true
            break
          }
        }
        if (!hasContent) keep[pendingBannerIdx] = false
      }
      pendingBannerIdx = i
    }
  }
  // 处理最后一个待定分隔符
  if (pendingBannerIdx >= 0) {
    let hasContent = false
    for (let j = pendingBannerIdx + 1; j < lines.length; j++) {
      if (keep[j] && !TEXT_BANNER_RE.test(lines[j])) {
        hasContent = true
        break
      }
    }
    if (!hasContent) keep[pendingBannerIdx] = false
  }

  const result = lines.filter((_, i) => keep[i])
  return result.join('<br/>')
}

/**
 * 文本样式「仅差异项」成对过滤：按 =============key============= 对齐左右分段。
 * 任一侧该段有差异则两侧都保留同名 banner；较短一侧补 blank 占位，避免后续 key 错位。
 */
export function filterDiffDataPaired(leftHtml, rightHtml) {
  const leftParsed = splitTextHtmlByBanners(leftHtml)
  const rightParsed = splitTextHtmlByBanners(rightHtml)

  // 无区域分隔时退回单侧过滤，再按行数补齐
  if (leftParsed.sections.length === 0 && rightParsed.sections.length === 0) {
    const leftLines = splitTextHtmlLines(filterDiffData(leftHtml))
    const rightLines = splitTextHtmlLines(filterDiffData(rightHtml))
    const maxLen = Math.max(leftLines.length, rightLines.length)
    return {
      left: padTextLinesToLength(leftLines, maxLen).join('<br/>'),
      right: padTextLinesToLength(rightLines, maxLen).join('<br/>'),
    }
  }

  const leftMap = new Map(leftParsed.sections.map((s) => [s.key, s]))
  const rightMap = new Map(rightParsed.sections.map((s) => [s.key, s]))
  const orderedKeys = []
  const seen = new Set()
  for (const s of leftParsed.sections) {
    if (!seen.has(s.key)) {
      seen.add(s.key)
      orderedKeys.push(s.key)
    }
  }
  for (const s of rightParsed.sections) {
    if (!seen.has(s.key)) {
      seen.add(s.key)
      orderedKeys.push(s.key)
    }
  }

  const outLeft = []
  const outRight = []

  const leftPreface = filterTextLinesKeepDiff(leftParsed.preface).filter((l) => isTextDiffLine(l))
  const rightPreface = filterTextLinesKeepDiff(rightParsed.preface).filter((l) => isTextDiffLine(l))
  if (leftPreface.length || rightPreface.length) {
    const maxPreface = Math.max(leftPreface.length, rightPreface.length)
    outLeft.push(...padTextLinesToLength(leftPreface, maxPreface))
    outRight.push(...padTextLinesToLength(rightPreface, maxPreface))
  }

  for (const key of orderedKeys) {
    const lSec = leftMap.get(key)
    const rSec = rightMap.get(key)
    const banner =
      (lSec && lSec.banner) ||
      (rSec && rSec.banner) ||
      `=============${key}=============`

    // 段内嵌套 banner 也参与配对：按「子分段」再对齐，避免算法等模式下内层标题错位
    const leftInner = splitBodyByNestedBanners(lSec ? lSec.lines : [])
    const rightInner = splitBodyByNestedBanners(rSec ? rSec.lines : [])
    const { leftLines: leftKeep, rightLines: rightKeep, hasDiff } = pairFilterInnerSegments(
      leftInner,
      rightInner
    )
    if (!hasDiff) continue

    const maxBody = Math.max(leftKeep.length, rightKeep.length, 1)
    outLeft.push(banner, ...padTextLinesToLength(leftKeep, maxBody))
    outRight.push(banner, ...padTextLinesToLength(rightKeep, maxBody))
  }

  return {
    left: outLeft.join('<br/>'),
    right: outRight.join('<br/>'),
  }
}

/**
 * 将 section 正文按嵌套 ============= 再切分；无嵌套则整段作为一个 body。
 * @returns {Array<{ banner: string|null, lines: string[] }>}
 */
function splitBodyByNestedBanners(lines) {
  const segs = []
  let cur = { banner: null, lines: [] }
  let started = false
  for (const line of lines || []) {
    if (TEXT_BANNER_RE.test(line) && parseTextBannerKey(line)) {
      if (started || cur.lines.length) segs.push(cur)
      cur = { banner: line, lines: [] }
      started = true
      continue
    }
    cur.lines.push(line)
  }
  if (started || cur.lines.length) segs.push(cur)
  if (segs.length === 0) segs.push({ banner: null, lines: [] })
  return segs
}

function pairFilterInnerSegments(leftInner, rightInner) {
  const maxSeg = Math.max(leftInner.length, rightInner.length)
  const outL = []
  const outR = []
  let hasDiff = false
  for (let i = 0; i < maxSeg; i += 1) {
    const lSeg = leftInner[i] || { banner: null, lines: [] }
    const rSeg = rightInner[i] || { banner: null, lines: [] }
    const lDiff = (lSeg.lines || []).filter((line) => isTextDiffLine(line))
    const rDiff = (rSeg.lines || []).filter((line) => isTextDiffLine(line))
    if (!lDiff.length && !rDiff.length) continue
    hasDiff = true
    if (lSeg.banner || rSeg.banner) {
      const b = lSeg.banner || rSeg.banner
      outL.push(b)
      outR.push(b)
    }
    const maxLen = Math.max(lDiff.length, rDiff.length)
    outL.push(...padTextLinesToLength(lDiff, maxLen))
    outR.push(...padTextLinesToLength(rDiff, maxLen))
  }
  return { leftLines: outL, rightLines: outR, hasDiff }
}

/**
 * 文本样式按 banner 对齐（不过滤内容）：两侧补齐缺失 section 与段内行数，供「显示全部」使用。
 */
export function alignTextHtmlByBanners(leftHtml, rightHtml) {
  const leftParsed = splitTextHtmlByBanners(leftHtml)
  const rightParsed = splitTextHtmlByBanners(rightHtml)
  if (leftParsed.sections.length === 0 && rightParsed.sections.length === 0) {
    const leftLines = splitTextHtmlLines(leftHtml)
    const rightLines = splitTextHtmlLines(rightHtml)
    const maxLen = Math.max(leftLines.length, rightLines.length)
    return {
      left: padTextLinesToLength(leftLines, maxLen).join('<br/>'),
      right: padTextLinesToLength(rightLines, maxLen).join('<br/>'),
    }
  }
  const leftMap = new Map(leftParsed.sections.map((s) => [s.key, s]))
  const rightMap = new Map(rightParsed.sections.map((s) => [s.key, s]))
  const orderedKeys = []
  const seen = new Set()
  for (const s of [...leftParsed.sections, ...rightParsed.sections]) {
    if (!seen.has(s.key)) {
      seen.add(s.key)
      orderedKeys.push(s.key)
    }
  }
  const outLeft = []
  const outRight = []
  const maxPreface = Math.max(leftParsed.preface.length, rightParsed.preface.length)
  if (maxPreface) {
    outLeft.push(...padTextLinesToLength(leftParsed.preface, maxPreface))
    outRight.push(...padTextLinesToLength(rightParsed.preface, maxPreface))
  }
  for (const key of orderedKeys) {
    const lSec = leftMap.get(key)
    const rSec = rightMap.get(key)
    const banner =
      (lSec && lSec.banner) ||
      (rSec && rSec.banner) ||
      `=============${key}=============`
    const lLines = lSec ? lSec.lines : []
    const rLines = rSec ? rSec.lines : []
    const maxBody = Math.max(lLines.length, rLines.length)
    outLeft.push(banner, ...padTextLinesToLength(lLines, maxBody))
    outRight.push(banner, ...padTextLinesToLength(rLines, maxBody))
  }
  return {
    left: outLeft.join('<br/>'),
    right: outRight.join('<br/>'),
  }
}

export function filterBannerData(input_data) {
  const lines = (typeof input_data === 'string' ? input_data.split('<br/>') : input_data)
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
  const result = lines.filter((line) =>
    /(banner_adunit|banner_interval|banner_events|ab_banner|banner|=============)/.test(line)
  )
  return result.join('<br/>')
}

/** ab_config 块：含 ae_sdk_config 和/或 ae_tiger_config（用于遍历） */
function looksLikeAbConfigBlock(k, v) {
  if (typeof k !== 'string' || v == null || typeof v !== 'object' || Array.isArray(v)) return false
  if (!/ab_config/i.test(k)) return false
  const ae = v.ae_sdk_config
  const tg = v.ae_tiger_config
  const hasSdk = ae != null && typeof ae === 'object' && !Array.isArray(ae)
  const hasTiger = tg != null && typeof tg === 'object' && !Array.isArray(tg)
  return hasSdk || hasTiger
}

function collectAlgorithmFromAeSdk(aeSdk, abPathPrefix, out) {
  if (aeSdk == null || typeof aeSdk !== 'object' || Array.isArray(aeSdk)) return
  for (const unitKey of Object.keys(aeSdk)) {
    if (!/^ad_unit_/i.test(unitKey)) continue
    const unit = aeSdk[unitKey]
    if (unit == null || typeof unit !== 'object' || Array.isArray(unit)) continue
    if (!Object.prototype.hasOwnProperty.call(unit, 'algorithm')) continue
    const id = `${abPathPrefix}.${unitKey}.algorithm`
    out[id] = unit.algorithm
  }
}

/**
 * 从单块区域 JSON 中提取：*.ab_config_* .ae_sdk_config .ad_unit_* .algorithm
 * 键名为展示用 id，如 ab_config_01.ad_unit_1
 * @param entryKey 当前 map 条目键（如 ab_config_01）；当 raw 已是 ab_config 内层（顶层含 ae_sdk_config）时用作 id 前缀
 */
export function extractAbConfigAlgorithmUnits(raw, entryKey = '') {
  const out = {}
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return out

  const aeTop = raw.ae_sdk_config
  if (aeTop != null && typeof aeTop === 'object' && !Array.isArray(aeTop)) {
    const prefix = entryKey || 'config'
    collectAlgorithmFromAeSdk(aeTop, prefix, out)
    return out
  }

  for (const k of Object.keys(raw)) {
    const v = raw[k]
    if (!looksLikeAbConfigBlock(k, v)) continue
    collectAlgorithmFromAeSdk(v.ae_sdk_config, k, out)
  }

  for (const wrapKey of Object.keys(raw)) {
    const wrapVal = raw[wrapKey]
    if (wrapVal == null || typeof wrapVal !== 'object' || Array.isArray(wrapVal)) continue
    if (looksLikeAbConfigBlock(wrapKey, wrapVal)) continue
    for (const innerKey of Object.keys(wrapVal)) {
      const innerVal = wrapVal[innerKey]
      if (!looksLikeAbConfigBlock(innerKey, innerVal)) continue
      collectAlgorithmFromAeSdk(innerVal.ae_sdk_config, `${wrapKey}.${innerKey}`, out)
    }
  }

  return out
}

/**
 * 从单块区域 JSON 中提取 ab_config_* .ae_tiger_config 整段对象（用于比对）
 * 分段 id：如 ab_config_01.ae_tiger_config
 */
export function extractAeTigerConfigUnits(raw, entryKey = '') {
  const out = {}
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return out

  const tigerTop = raw.ae_tiger_config
  if (tigerTop != null && typeof tigerTop === 'object' && !Array.isArray(tigerTop)) {
    const prefix = entryKey || 'config'
    out[`${prefix}.ae_tiger_config`] = tigerTop
    return out
  }

  for (const k of Object.keys(raw)) {
    const v = raw[k]
    if (!looksLikeAbConfigBlock(k, v)) continue
    const t = v.ae_tiger_config
    if (t != null && typeof t === 'object' && !Array.isArray(t)) {
      out[`${k}.ae_tiger_config`] = t
    }
  }

  for (const wrapKey of Object.keys(raw)) {
    const wrapVal = raw[wrapKey]
    if (wrapVal == null || typeof wrapVal !== 'object' || Array.isArray(wrapVal)) continue
    if (looksLikeAbConfigBlock(wrapKey, wrapVal)) continue
    for (const innerKey of Object.keys(wrapVal)) {
      const innerVal = wrapVal[innerKey]
      if (!looksLikeAbConfigBlock(innerKey, innerVal)) continue
      const t = innerVal.ae_tiger_config
      if (t != null && typeof t === 'object' && !Array.isArray(t)) {
        out[`${wrapKey}.${innerKey}.ae_tiger_config`] = t
      }
    }
  }

  return out
}

function algorithmToCompareObject(algo) {
  if (algo === undefined || algo === null) return {}
  if (typeof algo === 'object' && !Array.isArray(algo)) return algo
  return { value: algo }
}

export const ALGORITHM_EXTRACT_HINT =
  '期望路径：&lt;ab_config_*&gt;.ae_sdk_config.&lt;ad_unit_*&gt;.algorithm；若对象已是 ab_config 内层（顶层含 ae_sdk_config），分段前缀为当前区域键名（如 ab_config_01）。'

const MISSING_ALGORITHM_HTML = `<span class="diff-missing">未提取到 algorithm 节点。${ALGORITHM_EXTRACT_HINT}</span>`

export const TIGER_EXTRACT_HINT =
  '期望路径：&lt;ab_config_*&gt;.ae_tiger_config；若对象已是 ab_config 内层（顶层含 ae_tiger_config），分段 id 为 &lt;区域键&gt;.ae_tiger_config。'

const MISSING_TIGER_HTML = `<span class="diff-missing">未提取到 ae_tiger_config 节点。${TIGER_EXTRACT_HINT}</span>`

/**
 * 规范化 extracted units 的键：去除 entryKey 前缀，使得不同 ab_config 下的同名单元可以互相匹配。
 * 返回 suffix → { id: 原 fullId, value: 原值 } 的映射。
 */
export function normalizeUnitsForMatching(units, entryKey) {
  const norm = {}
  const prefix = entryKey ? entryKey + '.' : ''
  for (const [id, value] of Object.entries(units)) {
    const suffix = prefix && id.startsWith(prefix) ? id.slice(prefix.length) : id
    norm[suffix] = { id, value }
  }
  return norm
}

/**
 * 按 ae_tiger_config 分段比对两侧；无数据时输出「未提取到」提示
 */
export function buildTigerCompareHtml(leftRaw, rightRaw, options = {}) {
  const leftEntryKey = options.leftEntryKey ?? ''
  const rightEntryKey = options.rightEntryKey ?? ''
  const leftUnits = extractAeTigerConfigUnits(leftRaw, leftEntryKey)
  const rightUnits = extractAeTigerConfigUnits(rightRaw, rightEntryKey)

  // 规范化键以支持跨 ab_config 匹配
  const leftNorm = normalizeUnitsForMatching(leftUnits, leftEntryKey)
  const rightNorm = normalizeUnitsForMatching(rightUnits, rightEntryKey)
  const suffixes = [...new Set([...Object.keys(leftNorm), ...Object.keys(rightNorm)])].sort()

  if (suffixes.length === 0) {
    return { left: MISSING_TIGER_HTML, right: MISSING_TIGER_HTML, isEmpty: true }
  }

  let leftHtml = ''
  let rightHtml = ''
  for (const suffix of suffixes) {
    const lInfo = leftNorm[suffix]
    const rInfo = rightNorm[suffix]
    const lObj = algorithmToCompareObject(lInfo ? lInfo.value : undefined)
    const rObj = algorithmToCompareObject(rInfo ? rInfo.value : undefined)
    // 节点头用各自的原 ID，不存在时用对方 entryKey + suffix 兜底
    const lDisplayId = lInfo ? lInfo.id : ((rightEntryKey || 'config') + '.' + suffix)
    const rDisplayId = rInfo ? rInfo.id : ((leftEntryKey || 'config') + '.' + suffix)
    leftHtml += `=============${lDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'left')}<br/>`
    rightHtml += `=============${rDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'right')}<br/>`
  }
  return { left: leftHtml.trim(), right: rightHtml.trim(), isEmpty: false }
}

/**
 * 按 ad_unit 分段比对两侧 algorithm；无数据时左右均输出「未提取到」提示
 * @param options.leftEntryKey / rightEntryKey 对应各自 map 条目键，便于「内层 ae_sdk_config」形态下生成 ab_config_01.ad_unit_1 式 id
 */
export function buildAlgorithmCompareHtml(leftRaw, rightRaw, options = {}) {
  const leftEntryKey = options.leftEntryKey ?? ''
  const rightEntryKey = options.rightEntryKey ?? ''
  const leftUnits = extractAbConfigAlgorithmUnits(leftRaw, leftEntryKey)
  const rightUnits = extractAbConfigAlgorithmUnits(rightRaw, rightEntryKey)

  // 规范化键以支持跨 ab_config 匹配
  const leftNorm = normalizeUnitsForMatching(leftUnits, leftEntryKey)
  const rightNorm = normalizeUnitsForMatching(rightUnits, rightEntryKey)
  const suffixes = [...new Set([...Object.keys(leftNorm), ...Object.keys(rightNorm)])].sort()

  if (suffixes.length === 0) {
    return { left: MISSING_ALGORITHM_HTML, right: MISSING_ALGORITHM_HTML, isEmpty: true }
  }

  let leftHtml = ''
  let rightHtml = ''
  for (const suffix of suffixes) {
    const lInfo = leftNorm[suffix]
    const rInfo = rightNorm[suffix]
    const lObj = algorithmToCompareObject(lInfo ? lInfo.value : undefined)
    const rObj = algorithmToCompareObject(rInfo ? rInfo.value : undefined)
    // 节点头用各自的原 ID，不存在时用对方 entryKey + suffix 兜底
    const lDisplayId = lInfo ? lInfo.id : ((rightEntryKey || 'config') + '.' + suffix)
    const rDisplayId = rInfo ? rInfo.id : ((leftEntryKey || 'config') + '.' + suffix)
    leftHtml += `=============${lDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'left')}<br/>`
    rightHtml += `=============${rDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'right')}<br/>`
  }
  return { left: leftHtml.trim(), right: rightHtml.trim(), isEmpty: false }
}

/**
 * 从 ae_sdk_config 中收集 corridor_update 节点
 * 路径：ae_sdk_config.ad_unit_*.corridor_update
 */
function collectCorridorUpdateFromAeSdk(aeSdk, abPathPrefix, out) {
  if (aeSdk == null || typeof aeSdk !== 'object' || Array.isArray(aeSdk)) return
  for (const unitKey of Object.keys(aeSdk)) {
    if (!/^ad_unit_/i.test(unitKey)) continue
    const unit = aeSdk[unitKey]
    if (unit == null || typeof unit !== 'object' || Array.isArray(unit)) continue
    if (!Object.prototype.hasOwnProperty.call(unit, 'corridor_update')) continue
    const id = `${abPathPrefix}.${unitKey}.corridor_update`
    out[id] = unit.corridor_update
  }
}

/**
 * 从单块区域 JSON 中提取：*.ab_config_* .ae_sdk_config .ad_unit_* .corridor_update
 * 键名为展示用 id，如 ab_config_01.ad_unit_1.corridor_update
 * @param entryKey 当前 map 条目键（如 ab_config_01）；当 raw 已是 ab_config 内层时用作 id 前缀
 */
export function extractCorridorUpdateUnits(raw, entryKey = '') {
  const out = {}
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return out

  const aeTop = raw.ae_sdk_config
  if (aeTop != null && typeof aeTop === 'object' && !Array.isArray(aeTop)) {
    const prefix = entryKey || 'config'
    collectCorridorUpdateFromAeSdk(aeTop, prefix, out)
    return out
  }

  for (const k of Object.keys(raw)) {
    const v = raw[k]
    if (!looksLikeAbConfigBlock(k, v)) continue
    collectCorridorUpdateFromAeSdk(v.ae_sdk_config, k, out)
  }

  for (const wrapKey of Object.keys(raw)) {
    const wrapVal = raw[wrapKey]
    if (wrapVal == null || typeof wrapVal !== 'object' || Array.isArray(wrapVal)) continue
    if (looksLikeAbConfigBlock(wrapKey, wrapVal)) continue
    for (const innerKey of Object.keys(wrapVal)) {
      const innerVal = wrapVal[innerKey]
      if (!looksLikeAbConfigBlock(innerKey, innerVal)) continue
      collectCorridorUpdateFromAeSdk(innerVal.ae_sdk_config, `${wrapKey}.${innerKey}`, out)
    }
  }

  return out
}

export const CORRIDOR_UPDATE_EXTRACT_HINT =
  '期望路径：&lt;ab_config_*&gt;.ae_sdk_config.&lt;ad_unit_*&gt;.corridor_update；若对象已是 ab_config 内层（顶层含 ae_sdk_config），分段前缀为当前区域键名（如 ab_config_01）。'

const MISSING_CORRIDOR_UPDATE_HTML = `<span class="diff-missing">未提取到 corridor_update 节点。${CORRIDOR_UPDATE_EXTRACT_HINT}</span>`

/**
 * 按 corridor_update 分段比对两侧；无数据时输出「未提取到」提示
 */
export function buildCorridorUpdateCompareHtml(leftRaw, rightRaw, options = {}) {
  const leftEntryKey = options.leftEntryKey ?? ''
  const rightEntryKey = options.rightEntryKey ?? ''
  const leftUnits = extractCorridorUpdateUnits(leftRaw, leftEntryKey)
  const rightUnits = extractCorridorUpdateUnits(rightRaw, rightEntryKey)

  // 规范化键以支持跨 ab_config 匹配
  const leftNorm = normalizeUnitsForMatching(leftUnits, leftEntryKey)
  const rightNorm = normalizeUnitsForMatching(rightUnits, rightEntryKey)
  const suffixes = [...new Set([...Object.keys(leftNorm), ...Object.keys(rightNorm)])].sort()

  if (suffixes.length === 0) {
    return { left: MISSING_CORRIDOR_UPDATE_HTML, right: MISSING_CORRIDOR_UPDATE_HTML, isEmpty: true }
  }

  let leftHtml = ''
  let rightHtml = ''
  for (const suffix of suffixes) {
    const lInfo = leftNorm[suffix]
    const rInfo = rightNorm[suffix]
    const lObj = algorithmToCompareObject(lInfo ? lInfo.value : undefined)
    const rObj = algorithmToCompareObject(rInfo ? rInfo.value : undefined)
    const lDisplayId = lInfo ? lInfo.id : ((rightEntryKey || 'config') + '.' + suffix)
    const rDisplayId = rInfo ? rInfo.id : ((leftEntryKey || 'config') + '.' + suffix)
    leftHtml += `=============${lDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'left')}<br/>`
    rightHtml += `=============${rDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'right')}<br/>`
  }
  return { left: leftHtml.trim(), right: rightHtml.trim(), isEmpty: false }
}

// ---- corridor_set（地板设置）----

function collectCorridorSetFromAeSdk(aeSdk, abPathPrefix, out) {
  if (aeSdk == null || typeof aeSdk !== 'object' || Array.isArray(aeSdk)) return
  for (const unitKey of Object.keys(aeSdk)) {
    if (!/^ad_unit_/i.test(unitKey)) continue
    const unit = aeSdk[unitKey]
    if (unit == null || typeof unit !== 'object' || Array.isArray(unit)) continue
    if (!Object.prototype.hasOwnProperty.call(unit, 'corridor_set')) continue
    const id = `${abPathPrefix}.${unitKey}.corridor_set`
    out[id] = unit.corridor_set
  }
}

export function extractCorridorSetUnits(raw, entryKey = '') {
  const out = {}
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return out
  const aeTop = raw.ae_sdk_config
  if (aeTop != null && typeof aeTop === 'object' && !Array.isArray(aeTop)) {
    const prefix = entryKey || 'config'
    collectCorridorSetFromAeSdk(aeTop, prefix, out)
    return out
  }
  for (const k of Object.keys(raw)) {
    const v = raw[k]
    if (!looksLikeAbConfigBlock(k, v)) continue
    collectCorridorSetFromAeSdk(v.ae_sdk_config, k, out)
  }
  for (const wrapKey of Object.keys(raw)) {
    const wrapVal = raw[wrapKey]
    if (wrapVal == null || typeof wrapVal !== 'object' || Array.isArray(wrapVal)) continue
    if (looksLikeAbConfigBlock(wrapKey, wrapVal)) continue
    for (const innerKey of Object.keys(wrapVal)) {
      const innerVal = wrapVal[innerKey]
      if (!looksLikeAbConfigBlock(innerKey, innerVal)) continue
      collectCorridorSetFromAeSdk(innerVal.ae_sdk_config, `${wrapKey}.${innerKey}`, out)
    }
  }
  return out
}

export const CORRIDOR_SET_EXTRACT_HINT =
  '期望路径：&lt;ab_config_*&gt;.ae_sdk_config.&lt;ad_unit_*&gt;.corridor_set；若对象已是 ab_config 内层（顶层含 ae_sdk_config），分段前缀为当前区域键名（如 ab_config_01）。'

const MISSING_CORRIDOR_SET_HTML = `<span class="diff-missing">未提取到 corridor_set 节点。${CORRIDOR_SET_EXTRACT_HINT}</span>`

export function buildCorridorSetCompareHtml(leftRaw, rightRaw, options = {}) {
  const leftEntryKey = options.leftEntryKey ?? ''
  const rightEntryKey = options.rightEntryKey ?? ''
  const leftUnits = extractCorridorSetUnits(leftRaw, leftEntryKey)
  const rightUnits = extractCorridorSetUnits(rightRaw, rightEntryKey)

  // 规范化键以支持跨 ab_config 匹配
  const leftNorm = normalizeUnitsForMatching(leftUnits, leftEntryKey)
  const rightNorm = normalizeUnitsForMatching(rightUnits, rightEntryKey)
  const suffixes = [...new Set([...Object.keys(leftNorm), ...Object.keys(rightNorm)])].sort()
  if (suffixes.length === 0) {
    return { left: MISSING_CORRIDOR_SET_HTML, right: MISSING_CORRIDOR_SET_HTML, isEmpty: true }
  }
  let leftHtml = ''
  let rightHtml = ''
  for (const suffix of suffixes) {
    const lInfo = leftNorm[suffix]
    const rInfo = rightNorm[suffix]
    const lObj = algorithmToCompareObject(lInfo ? lInfo.value : undefined)
    const rObj = algorithmToCompareObject(rInfo ? rInfo.value : undefined)
    const lDisplayId = lInfo ? lInfo.id : ((rightEntryKey || 'config') + '.' + suffix)
    const rDisplayId = rInfo ? rInfo.id : ((leftEntryKey || 'config') + '.' + suffix)
    leftHtml += `=============${lDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'left')}<br/>`
    rightHtml += `=============${rDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'right')}<br/>`
  }
  return { left: leftHtml.trim(), right: rightHtml.trim(), isEmpty: false }
}

// ---- reload（重试）----

function collectReloadFromAeSdk(aeSdk, abPathPrefix, out) {
  if (aeSdk == null || typeof aeSdk !== 'object' || Array.isArray(aeSdk)) return
  for (const unitKey of Object.keys(aeSdk)) {
    if (!/^ad_unit_/i.test(unitKey)) continue
    const unit = aeSdk[unitKey]
    if (unit == null || typeof unit !== 'object' || Array.isArray(unit)) continue
    if (!Object.prototype.hasOwnProperty.call(unit, 'reload')) continue
    const id = `${abPathPrefix}.${unitKey}.reload`
    out[id] = unit.reload
  }
}

export function extractReloadUnits(raw, entryKey = '') {
  const out = {}
  if (raw == null || typeof raw !== 'object' || Array.isArray(raw)) return out
  const aeTop = raw.ae_sdk_config
  if (aeTop != null && typeof aeTop === 'object' && !Array.isArray(aeTop)) {
    const prefix = entryKey || 'config'
    collectReloadFromAeSdk(aeTop, prefix, out)
    return out
  }
  for (const k of Object.keys(raw)) {
    const v = raw[k]
    if (!looksLikeAbConfigBlock(k, v)) continue
    collectReloadFromAeSdk(v.ae_sdk_config, k, out)
  }
  for (const wrapKey of Object.keys(raw)) {
    const wrapVal = raw[wrapKey]
    if (wrapVal == null || typeof wrapVal !== 'object' || Array.isArray(wrapVal)) continue
    if (looksLikeAbConfigBlock(wrapKey, wrapVal)) continue
    for (const innerKey of Object.keys(wrapVal)) {
      const innerVal = wrapVal[innerKey]
      if (!looksLikeAbConfigBlock(innerKey, innerVal)) continue
      collectReloadFromAeSdk(innerVal.ae_sdk_config, `${wrapKey}.${innerKey}`, out)
    }
  }
  return out
}

export const RELOAD_EXTRACT_HINT =
  '期望路径：&lt;ab_config_*&gt;.ae_sdk_config.&lt;ad_unit_*&gt;.reload；若对象已是 ab_config 内层（顶层含 ae_sdk_config），分段前缀为当前区域键名（如 ab_config_01）。'

const MISSING_RELOAD_HTML = `<span class="diff-missing">未提取到 reload 节点。${RELOAD_EXTRACT_HINT}</span>`

export function buildReloadCompareHtml(leftRaw, rightRaw, options = {}) {
  const leftEntryKey = options.leftEntryKey ?? ''
  const rightEntryKey = options.rightEntryKey ?? ''
  const leftUnits = extractReloadUnits(leftRaw, leftEntryKey)
  const rightUnits = extractReloadUnits(rightRaw, rightEntryKey)

  // 规范化键以支持跨 ab_config 匹配
  const leftNorm = normalizeUnitsForMatching(leftUnits, leftEntryKey)
  const rightNorm = normalizeUnitsForMatching(rightUnits, rightEntryKey)
  const suffixes = [...new Set([...Object.keys(leftNorm), ...Object.keys(rightNorm)])].sort()
  if (suffixes.length === 0) {
    return { left: MISSING_RELOAD_HTML, right: MISSING_RELOAD_HTML, isEmpty: true }
  }
  let leftHtml = ''
  let rightHtml = ''
  for (const suffix of suffixes) {
    const lInfo = leftNorm[suffix]
    const rInfo = rightNorm[suffix]
    const lObj = algorithmToCompareObject(lInfo ? lInfo.value : undefined)
    const rObj = algorithmToCompareObject(rInfo ? rInfo.value : undefined)
    const lDisplayId = lInfo ? lInfo.id : ((rightEntryKey || 'config') + '.' + suffix)
    const rDisplayId = rInfo ? rInfo.id : ((leftEntryKey || 'config') + '.' + suffix)
    leftHtml += `=============${lDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'left')}<br/>`
    rightHtml += `=============${rDisplayId}=============<br/>${compareJsonTree(lObj, rObj, 'right')}<br/>`
  }
  return { left: leftHtml.trim(), right: rightHtml.trim(), isEmpty: false }
}

export function extractRegionData(map, key) {
  return map?.[key] ?? {}
}

/**
 * 多区域「全部」比对：按键名匹配合并左右区域键，按字母序排列，
 * 同一键名的左右数据配对比对。左右两侧均使用同一键名作标题分隔符，确保对齐。
 * json_type===1 算法；json_type===2 老虎机 ae_tiger_config；3 corridor_update；4 corridor_set；5 reload
 */
export function pickJsonRegions(left_map, right_map, json_type = 0) {
  // 合并左右区域键并按字母排序，确保同一键名在两侧同位置出现
  const allKeys = [...new Set([
    ...Object.keys(left_map || {}),
    ...Object.keys(right_map || {}),
  ])].sort()
  let renderedLeft = ''
  let renderedRight = ''

  for (const key of allKeys) {
    const leftRaw = (left_map || {})[key]
    const rightRaw = (right_map || {})[key]

    if (json_type === 1) {
      const { left, right } = buildAlgorithmCompareHtml(leftRaw, rightRaw, {
        leftEntryKey: key,
        rightEntryKey: key,
      })
      renderedLeft += `=============${key}=============<br/>${left}<br/>`
      renderedRight += `=============${key}=============<br/>${right}<br/>`
      continue
    }
    if (json_type === 2) {
      const { left, right } = buildTigerCompareHtml(leftRaw, rightRaw, {
        leftEntryKey: key,
        rightEntryKey: key,
      })
      renderedLeft += `=============${key}=============<br/>${left}<br/>`
      renderedRight += `=============${key}=============<br/>${right}<br/>`
      continue
    }
    if (json_type === 3) {
      const { left, right } = buildCorridorUpdateCompareHtml(leftRaw, rightRaw, {
        leftEntryKey: key,
        rightEntryKey: key,
      })
      renderedLeft += `=============${key}=============<br/>${left}<br/>`
      renderedRight += `=============${key}=============<br/>${right}<br/>`
      continue
    }
    if (json_type === 4) {
      const { left, right } = buildCorridorSetCompareHtml(leftRaw, rightRaw, {
        leftEntryKey: key,
        rightEntryKey: key,
      })
      renderedLeft += `=============${key}=============<br/>${left}<br/>`
      renderedRight += `=============${key}=============<br/>${right}<br/>`
      continue
    }
    if (json_type === 5) {
      const { left, right } = buildReloadCompareHtml(leftRaw, rightRaw, {
        leftEntryKey: key,
        rightEntryKey: key,
      })
      renderedLeft += `=============${key}=============<br/>${left}<br/>`
      renderedRight += `=============${key}=============<br/>${right}<br/>`
      continue
    }
    const leftChunk = leftRaw != null ? extractRegionData(left_map, key) : {}
    const rightChunk = rightRaw != null ? extractRegionData(right_map, key) : {}
    const left_result = compareJsonTree(leftChunk, rightChunk, 'left')
    const right_result = compareJsonTree(leftChunk, rightChunk, 'right')
    renderedLeft += `=============${key}=============<br/>${left_result}<br/>`
    renderedRight += `=============${key}=============<br/>${right_result}<br/>`
  }
  return {
    left: renderedLeft.trim(),
    right: renderedRight.trim(),
  }
}

export function groupByFirstLetter(data) {
  const groups = {}
  ;(data || []).forEach((item) => {
    if (!item || !item.length) return
    const firstLetter = item[0].toUpperCase()
    if (!groups[firstLetter]) {
      groups[firstLetter] = { label: firstLetter, options: [] }
    }
    groups[firstLetter].options.push({ value: item, label: item })
  })
  return Object.values(groups)
}

export function mergeHtmlParts(a, b, sep = '<br/><hr class="diff-sep" /><br/>') {
  if (!a) return b || ''
  if (!b) return a || ''
  return a + sep + b
}

/**
 * 将文本视图的 &lt;br/&gt; 分隔输出转换为结构化 &lt;div&gt; 行。
 * 分隔符行使用内联样式（与 JSON 视图 section 视觉效果一致），确保全宽居中显示。
 * blank 占位行保留等高，用于左右按 key 对齐。
 */
export function wrapTextAsStructuredHtml(html) {
  if (!html) return ''
  const SECTION_STYLE = 'background:linear-gradient(90deg,#ddf4ff 0%,#f6f8fa 55%,#f6f8fa 100%);border:1px solid #b6e0fe;border-radius:6px;padding:6px 10px;margin:10px 0 6px;text-align:center;font-weight:600;font-size:13px;color:#0550ae;font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:block'
  const LINE_STYLE = 'min-height:24px;line-height:1.72;padding:0 2px;border-radius:4px'
  const BLANK_STYLE = `${LINE_STYLE};visibility:hidden`

  const lines = html.split('<br/>')
  const wrapped = lines
    .map((line) => {
      const trimmed = line.trim()
      if (!trimmed) return ''
      if (/=============/.test(trimmed)) {
        return `<div style="${SECTION_STYLE}">${trimmed}</div>`
      }
      if (/diff-blank/.test(trimmed)) {
        return `<div class="diff-text-blank" style="${BLANK_STYLE}">${TEXT_DIFF_BLANK_LINE}</div>`
      }
      return `<div style="${LINE_STYLE}">${trimmed}</div>`
    })
    .filter(Boolean)
    .join('')
  return wrapped
}
