<template>
  <div class="config-compare">
    <el-card class="filter-card" shadow="never">
      <template #header>
        <div class="card-title">
          <span class="title-text">配置文件比对</span>
          <el-tag size="small" type="info" effect="plain">选择项目与方案后，左右两侧将展示差异</el-tag>
        </div>
      </template>

      <el-form label-position="top" class="filter-form" @submit.prevent>
        <el-row :gutter="24" class="global-filter-row">
          <el-col :xs="24" :lg="15">
            <el-form-item label="项目名称" required class="project-form-item">
              <div class="project-select-row">
                <el-select
                  v-model="st.select_projects"
                  class="project-select"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  :max-collapse-tags="2"
                  filterable
                  placeholder="搜索或选择项目（可多选）"
                  :teleported="true"
                  @change="onProjectsChange"
                >
                  <el-option-group
                    v-for="group in projectSelectGroups"
                    :key="group.key"
                    :label="group.label"
                  >
                    <el-option
                      v-for="opt in group.options"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                    />
                  </el-option-group>
                </el-select>
                <span class="project-platform-tag" :class="currentProjectPlatform">
                  {{ projectPlatformTagText }}
                </span>
                <el-button
                  type="warning"
                  plain
                  class="sync-cache-btn"
                  :loading="loading.files"
                  :disabled="!selectedProjects.length || loading.files"
                  @click="onSyncAdwaynumCache"
                >
                  手动同步缓存
                </el-button>
              </div>
              <p class="project-hint">
                请先选择至少一个项目；可多选，方案列表与搜索仅在已选项目范围内进行。
              </p>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :lg="9" class="screenshot-col">
            <el-form-item label="&#8203;" class="screenshot-form-item">
              <div class="screenshot-action-row">
                <el-button
                  type="primary"
                  class="screenshot-btn"
                  :loading="loading.screenshot"
                  @click="onCaptureScreenshot"
                >
                  截图
                </el-button>
              </div>
              <p class="screenshot-hint">截图对比源与比对结果区域图片</p>
            </el-form-item>
          </el-col>
        </el-row>

        <div class="display-options-wrap">
          <el-divider content-position="left" class="section-divider">
            <span class="section-divider-text">比对设置</span>
          </el-divider>
          <div class="display-options-panel">
            <el-form-item label="比对模式" required class="display-mode-item">
              <el-radio-group v-model="st.compare_mode" class="display-mode-group" @change="onCompareModeChange">
                <el-radio-button value="single">对比源</el-radio-button>
                <el-radio-button value="batch">批量比对</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="显示方式" required class="display-mode-item">
              <el-radio-group
                v-model="st.is_show_discrepancy"
                class="display-mode-group"
                :disabled="isBatchMode"
                @change="onDisplayModeChange"
              >
                <el-radio-button value="is_show_all" :disabled="isBatchMode">全部显示</el-radio-button>
                <el-radio-button value="is_show_diff">仅差异项</el-radio-button>
                <el-radio-button value="is_show_banner" :disabled="isBatchMode">仅 Banner</el-radio-button>
                <el-radio-button value="is_show_algorithm" :disabled="isBatchMode">显示算法</el-radio-button>
                <el-radio-button value="is_show_tiger" :disabled="isBatchMode">显示老虎机</el-radio-button>
                <el-radio-button value="is_show_corridor" :disabled="isBatchMode">显示地板更新</el-radio-button>
                <el-radio-button value="is_show_corridor_set" :disabled="isBatchMode">显示地板设置</el-radio-button>
                <el-radio-button value="is_show_reload" :disabled="isBatchMode">显示重试</el-radio-button>
              </el-radio-group>
              <p v-if="isBatchMode" class="form-hint">批量比对固定为「仅差异项」。</p>
            </el-form-item>
            <el-form-item label="结果样式" required class="display-mode-item">
              <el-radio-group
                v-model="st.result_render_style"
                class="display-mode-group"
                :disabled="isBatchMode"
                @change="runCompare"
              >
                <el-radio-button value="text_view">文本样式</el-radio-button>
                <el-radio-button value="json_view" :disabled="isBatchMode">JSON 样式</el-radio-button>
              </el-radio-group>
              <p v-if="isBatchMode" class="form-hint">批量比对固定为「文本样式」。</p>
            </el-form-item>
          </div>
        </div>

        <div ref="compareSourcesRef" class="compare-sources-wrap">
        <el-divider content-position="left" class="section-divider">
          <span class="section-divider-text">{{ isBatchMode ? '批量比对' : '对比源' }}</span>
        </el-divider>

        <el-alert
          v-if="loading.files"
          class="scheme-status-alert"
          type="info"
          :closable="false"
          show-icon
          title="正在加载方案列表…"
        />

        <el-row v-if="!isBatchMode" :gutter="24" class="compare-sources">
          <el-col :xs="24" :lg="12">
            <div class="source-panel">
            <div class="source-head">
              <span class="source-badge left">左</span>
              <span class="source-title">对比源 A</span>
            </div>
            <el-form-item label="时间段" required>
              <el-radio-group v-model="st.leftTimeslot" class="slot-radios" @change="onLeftSlotChange">
                <el-radio-button value="left_time_slot_0">全部</el-radio-button>
                <el-radio-button value="left_time_slot_1">0–7 天</el-radio-button>
                <el-radio-button value="left_time_slot_2">7–31 天</el-radio-button>
                <el-radio-button value="left_time_slot_3">31 天+</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="方案" required>
              <el-select
                v-model="st.select_left_Adwaynum"
                placeholder="请选择或输入关键字筛选方案"
                filterable
                clearable
                class="scheme-select w-full"
                popper-class="scheme-select-dropdown"
                fit-input-width
                :loading="loading.files || loading.json"
                :filter-method="onLeftSchemeFilter"
                @visible-change="onLeftSchemeSelectVisible"
                @clear="onLeftSchemeFilter('')"
                @change="getLeftadwaynumJson"
              >
                <template #label="{ label }">
                  <span class="scheme-select-trigger-label">{{ label }}</span>
                </template>
                <el-option
                  v-for="item in leftSchemeOptionsForSelect"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                >
                  <span class="scheme-option-label">{{ item.label }}</span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item v-if="regionKeysLeft.length" label="区域">
              <el-radio-group v-model="st.left_region" class="region-radios" @change="runCompare">
                <template v-for="group in getRegionGroups(regionKeysLeft)" :key="group.primary || '其他'">
                  <div class="region-group-block">
                    <span v-if="group.primary" class="region-group-tag">{{ group.primary }}</span>
                    <div class="region-subs" :class="{ 'region-subs-no-tag': !group.primary }">
                      <div class="region-sub-row" v-for="sub in group.subGroups" :key="sub.name">
                        <span v-if="SUB_LABELS[sub.name]" class="region-sub-tag">{{ SUB_LABELS[sub.name] }}</span>
                        <el-radio v-for="key in sub.keys" :key="key" :value="key">{{ key }}</el-radio>
                      </div>
                    </div>
                  </div>
                </template>
                <div class="region-group-block">
                  <span class="region-group-tag"></span>
                  <div class="region-subs"><div class="region-sub-row"><el-radio value="all">全部</el-radio></div></div>
                </div>
              </el-radio-group>
            </el-form-item>
            </div>
          </el-col>

          <el-col :xs="24" :lg="12">
            <div class="source-panel">
            <div class="source-head">
              <span class="source-badge right">右</span>
              <span class="source-title">对比源 B</span>
            </div>
            <el-form-item label="时间段" required>
              <el-radio-group v-model="st.rightTimeslot" class="slot-radios" @change="onRightSlotChange">
                <el-radio-button value="right_time_slot_0">全部</el-radio-button>
                <el-radio-button value="right_time_slot_1">0–7 天</el-radio-button>
                <el-radio-button value="right_time_slot_2">7–31 天</el-radio-button>
                <el-radio-button value="right_time_slot_3">31 天+</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="方案" required>
              <el-select
                v-model="st.select_right_Adwaynum"
                placeholder="请选择或输入关键字筛选方案"
                filterable
                clearable
                class="scheme-select w-full"
                popper-class="scheme-select-dropdown"
                fit-input-width
                :loading="loading.files || loading.json"
                :filter-method="onRightSchemeFilter"
                @visible-change="onRightSchemeSelectVisible"
                @clear="onRightSchemeFilter('')"
                @change="getRightadwaynumJson"
              >
                <template #label="{ label }">
                  <span class="scheme-select-trigger-label">{{ label }}</span>
                </template>
                <el-option
                  v-for="item in rightSchemeOptionsForSelect"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                >
                  <span class="scheme-option-label">{{ item.label }}</span>
                </el-option>
              </el-select>
            </el-form-item>
            <el-form-item v-if="regionKeysRight.length" label="区域">
              <el-radio-group v-model="st.right_region" class="region-radios" @change="runCompare">
                <template v-for="group in getRegionGroups(regionKeysRight)" :key="group.primary || '其他'">
                  <div class="region-group-block">
                    <span v-if="group.primary" class="region-group-tag">{{ group.primary }}</span>
                    <div class="region-subs" :class="{ 'region-subs-no-tag': !group.primary }">
                      <div class="region-sub-row" v-for="sub in group.subGroups" :key="sub.name">
                        <span v-if="SUB_LABELS[sub.name]" class="region-sub-tag">{{ SUB_LABELS[sub.name] }}</span>
                        <el-radio v-for="key in sub.keys" :key="'rr-' + key" :value="key">{{ key }}</el-radio>
                      </div>
                    </div>
                  </div>
                </template>
                <div class="region-group-block">
                  <span class="region-group-tag"></span>
                  <div class="region-subs"><div class="region-sub-row"><el-radio value="all">全部</el-radio></div></div>
                </div>
              </el-radio-group>
            </el-form-item>
            </div>
          </el-col>
        </el-row>

        <template v-else>
          <el-alert
            class="scheme-status-alert"
            type="info"
            :closable="false"
            show-icon
            title="按序号一一配对比对：左侧第 1 个方案号对右侧第 1 个，以此类推；区域固定为「全部」，仅展示差异项、文本样式。"
          />
          <el-row :gutter="24" class="compare-sources">
            <el-col :xs="24" :lg="12">
              <div class="source-panel">
                <div class="source-head">
                  <span class="source-badge left">左</span>
                  <span class="source-title">批量方案 A</span>
                </div>
                <el-form-item label="时间段" required>
                  <el-radio-group v-model="st.leftTimeslot" class="slot-radios">
                    <el-radio-button value="left_time_slot_0">全部</el-radio-button>
                    <el-radio-button value="left_time_slot_1">0–7 天</el-radio-button>
                    <el-radio-button value="left_time_slot_2">7–31 天</el-radio-button>
                    <el-radio-button value="left_time_slot_3">31 天+</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="方案号" required>
                  <el-input
                    v-model="st.batch_left_input"
                    type="textarea"
                    :rows="5"
                    placeholder="粘贴多个方案号，空格或换行分隔&#10;例如：fs1001 fs1002 fs1003"
                  />
                </el-form-item>
                <el-form-item label="区域">
                  <el-tag type="info" effect="plain">全部（固定）</el-tag>
                </el-form-item>
              </div>
            </el-col>
            <el-col :xs="24" :lg="12">
              <div class="source-panel">
                <div class="source-head">
                  <span class="source-badge right">右</span>
                  <span class="source-title">批量方案 B</span>
                </div>
                <el-form-item label="时间段" required>
                  <el-radio-group v-model="st.rightTimeslot" class="slot-radios">
                    <el-radio-button value="right_time_slot_0">全部</el-radio-button>
                    <el-radio-button value="right_time_slot_1">0–7 天</el-radio-button>
                    <el-radio-button value="right_time_slot_2">7–31 天</el-radio-button>
                    <el-radio-button value="right_time_slot_3">31 天+</el-radio-button>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="方案号" required>
                  <el-input
                    v-model="st.batch_right_input"
                    type="textarea"
                    :rows="5"
                    placeholder="粘贴多个方案号，空格或换行分隔&#10;例如：fs1011 fs1012 fs1013"
                  />
                </el-form-item>
                <el-form-item label="区域">
                  <el-tag type="info" effect="plain">全部（固定）</el-tag>
                </el-form-item>
              </div>
            </el-col>
          </el-row>
          <div class="batch-actions">
            <el-button type="primary" :loading="loading.compare" @click="runBatchCompare">
              开始批量比对
            </el-button>
          </div>
        </template>
        </div>
      </el-form>
    </el-card>

    <div ref="resultSectionRef" class="result-section">
      <div class="result-section-head">
        <span class="result-section-title">比对结果</span>
        <span class="result-section-sub">左右分栏，可独立滚动查看</span>
      </div>
      <div class="result-row">
      <el-card class="result-pane" shadow="hover">
        <template #header>
          <span class="pane-title">左侧输出</span>
        </template>
        <el-skeleton v-if="loading.compare" :rows="8" animated />
        <div v-else-if="st.result_render_style === 'text_view'" class="diff-html" v-html="st.renderedLeftJson || emptyHint"></div>
        <div v-else class="diff-html diff-json-pre" v-html="st.renderedLeftJson || jsonEmptyHintHtml"></div>
      </el-card>
      <el-card class="result-pane" shadow="hover">
        <template #header>
          <span class="pane-title">右侧输出</span>
        </template>
        <el-skeleton v-if="loading.compare" :rows="8" animated />
        <div v-else-if="st.result_render_style === 'text_view'" class="diff-html" v-html="st.renderedRightJson || emptyHint"></div>
        <div v-else class="diff-html diff-json-pre" v-html="st.renderedRightJson || jsonEmptyHintHtml"></div>
      </el-card>
      </div>
    </div>

    <!-- 悬浮 AI 助手按钮 -->
    <div class="ai-float-btn" title="AI 助手" @click="aiChatVisible = true">
      <svg class="ai-robot-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="10" y="22" width="28" height="20" rx="4" fill="white" stroke="white" stroke-width="0.5"/>
        <rect x="18" y="8" width="12" height="16" rx="5" fill="white"/>
        <circle cx="21" cy="16" r="2.5" fill="#409eff"/>
        <circle cx="27" cy="16" r="2.5" fill="#409eff"/>
        <rect x="21" y="28" width="6" height="2" rx="1" fill="#409eff"/>
        <rect x="15" y="32" width="18" height="4" rx="1.5" fill="#409eff"/>
        <circle cx="16" cy="6" r="2" fill="white"/>
        <rect x="14" y="11" width="4" height="6" rx="2" fill="white"/>
        <circle cx="32" cy="6" r="2" fill="white"/>
        <rect x="30" y="11" width="4" height="6" rx="2" fill="white"/>
      </svg>
    </div>

    <!-- AI 对话对话框 -->
    <AiChatDialog v-model:visible="aiChatVisible" />
  </div>
</template>

<script setup>
import { reactive, computed, nextTick, ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import html2canvas from 'html2canvas'
import {
  get_adwaynum_file,
  get_adwaynum_json_2,
  rebuild_adwaynum_cache,
  report_statistic_info,
} from '../../api/tools/gitConfigDiff.js'
import { getUserCnName } from '../../common/request.js'
import { diffLines } from 'diff'
import AiChatDialog from '../../components/AiChatDialog.vue'
import {
  compareJsonTree,
  buildAlgorithmCompareHtml,
  buildTigerCompareHtml,
  buildCorridorUpdateCompareHtml,
  buildCorridorSetCompareHtml,
  buildReloadCompareHtml,
  extractAbConfigAlgorithmUnits,
  extractAeTigerConfigUnits,
  extractCorridorUpdateUnits,
  extractCorridorSetUnits,
  extractReloadUnits,
  extractRegionData,
  filterDiffData,
  filterDiffDataPaired,
  alignTextHtmlByBanners,
  filterBannerData,
  pickJsonRegions,
  normalizeCrossConfigViewData,
  normalizeUnitsForMatching,
  wrapTextAsStructuredHtml,
} from '../../utils/configCompareDiff.js'

/**
 * 配置比对项目列表（静态数据，不依赖接口）
 * name：后端 / git 目录名，可含 ab3.5 等带点号的真实目录名
 * label：下拉展示名
 */
const COMPARE_PROJECTS = Object.freeze([
  { name: 'gp_blockblast', label: 'GP方块' },
  { name: 'gp_blockblast_rn', label: 'GP方块-rn' },
  { name: 'gp_blockblast_orth', label: 'GP方块-AB' },
  { name: 'gp_blockblast_ml', label: 'GP方块-互斥' },
  { name: 'gp_taptile', label: 'GP-taptile' },
  { name: 'gp_taptile_orth', label: 'GP-taptile-AB' },
  { name: 'gp_mahjongblast', label: 'GP方块麻将' },
  { name: 'gp_mahjongblast_orth', label: 'GP方块麻将-AB' },
  { name: 'gp_mahjong_3he', label: 'GP国风麻将' },
  { name: 'gp_sudoku', label: 'GP数独' },
  { name: 'gp_mahjong', label: 'GP麻将' },
  { name: 'gp_mahjong_rn', label: 'GP麻将-rn' },
  { name: 'gp_mahjong_orth', label: 'GP麻将-AB' },
  { name: 'gp_blockcrush', label: 'GP木块' },
  { name: 'gp_blockcrush_rn', label: 'GP木块-rn' },
  { name: 'gp_blockcrush_orth', label: 'GP木块-AB' },
  { name: 'gp_blockcrush_me', label: 'GP木块-ME' },
  { name: 'gp_blocknova', label: 'GPnova' },
  { name: 'gp_sandcursh', label: 'GP沙块' },
  { name: 'ios_blcokblast', label: 'IOS方块' },
  { name: 'ios_blcokblast_ab3.5_orth', label: 'IOS方块-AB3.5' },
  { name: 'ios_blcokblast_rn', label: 'IOS方块-rn' },
  { name: 'ios_mahjong_3he', label: 'IOS国风麻将' },
  { name: 'ios_blockcrush', label: 'IOS木块' },
  { name: 'ios_mahjong', label: 'IOS麻将' },
  { name: 'ios_sandcrush', label: 'IOS沙块' },
  { name: 'ios_sudoku', label: 'IOS数独' },
])

const COMPARE_PROJECT_LABEL_BY_NAME = Object.freeze(
  Object.fromEntries(COMPARE_PROJECTS.map(({ name, label }) => [name, label])),
)

const emptyHint =
  '<p class="empty-hint">请先完成左侧、右侧方案选择；两侧区域数据就绪后将自动比对。</p>'
const jsonEmptyHintHtml = '<div class="diff-json-line diff-json-line-empty">请先完成左侧、右侧方案选择；两侧区域数据就绪后将自动比对。</div>'
const jsonDiffNoDiffHintHtml =
  '<div class="diff-json-line diff-json-line-empty">当前为「仅差异项」：两侧 JSON 行级比对无差异（或所选片段完全相同）。</div>'
/** 方案下拉最多展示条数（全量仍保留在内存，仅录入关键字时从全量筛选） */
const SCHEME_DROPDOWN_CAP = 100
/** 方案选项 value：project + 分隔符 + 方案名，用于多项目下区分同名方案 */
const SCHEME_VALUE_SEP = '\x1f'
const adwaynumFileCache = new Map()

const compareSourcesRef = ref(null)
const resultSectionRef = ref(null)
const aiChatVisible = ref(false)

const loading = reactive({
  files: false,
  json: false,
  compare: false,
  screenshot: false,
})

const st = reactive({
  compare_mode: 'single',
  select_projects: [],
  is_show_discrepancy: 'is_show_all',
  result_render_style: 'text_view',
  batch_left_input: '',
  batch_right_input: '',
  /** 切回对比源时恢复单条比对下的显示/样式设置 */
  _single_discrepancy_backup: '',
  _single_render_style_backup: '',
  leftTimeslot: 'left_time_slot_0',
  left_region: '',
  select_left_Adwaynum: '',
  rightTimeslot: 'right_time_slot_0',
  right_region: '',
  select_right_Adwaynum: '',
  api_left_region_map: {},
  api_right_region_map: {},
  renderedLeftJson: '',
  renderedRightJson: '',
  /** 已选项目合并后的方案项（下拉筛选仅在此列表内进行） */
  left_scheme_entries: [],
  right_scheme_entries: [],
  left_scheme_filter_query: '',
  right_scheme_filter_query: '',
})

const isBatchMode = computed(() => st.compare_mode === 'batch')

const regionKeysLeft = computed(() => Object.keys(st.api_left_region_map || {}))
const regionKeysRight = computed(() => Object.keys(st.api_right_region_map || {}))

/** 二级子组标签 */
const SUB_LABELS = { abConfig: 'AB', extra: 'Ex', installDay: '天', others: '' }

/**
 * 两级分组：
 * 1. 一级：按 banner-- / insert-- / reward-- 前缀归类，无前缀归入「其他」
 * 2. 二级：每组内按 ab_config / extra / install_day 划分子组
 * 仅有一个「其他」组时隐藏其标签。
 */
function getRegionGroups(keys) {
  const sorted = [...keys].sort()
  const primaryMap = new Map()

  for (const key of sorted) {
    let primary
    if (key.startsWith('banner--')) primary = 'banner'
    else if (key.startsWith('insert--')) primary = 'insert'
    else if (key.startsWith('reward--')) primary = 'reward'
    else primary = '其他'

    if (!primaryMap.has(primary)) {
      primaryMap.set(primary, { abConfig: [], extra: [], installDay: [], others: [] })
    }

    const sub = primaryMap.get(primary)
    if (/ab_config/i.test(key)) sub.abConfig.push(key)
    else if (/extra/i.test(key)) sub.extra.push(key)
    else if (/install_day/i.test(key)) sub.installDay.push(key)
    else sub.others.push(key)
  }

  const order = ['banner', 'insert', 'reward', '其他']
  const result = []
  const onlyOthers = primaryMap.size === 1 && primaryMap.has('其他')
  for (const p of order) {
    if (!primaryMap.has(p)) continue
    const sub = primaryMap.get(p)
    const subGroups = []
    for (const sn of ['abConfig', 'extra', 'installDay', 'others']) {
      if (sub[sn].length) subGroups.push({ name: sn, keys: sub[sn] })
    }
    // 仅「其他」组时标签置空
    result.push({ primary: onlyOthers ? '' : p, subGroups })
  }
  return result
}

const projectSelectGroups = computed(() => {
  const entries = COMPARE_PROJECTS.map(({ name, label }) => ({ value: name, label }))
  return [
    {
      key: 'gp',
      label: 'Google Play（GP）',
      options: entries.filter((x) => !x.value.startsWith('ios_')),
    },
    {
      key: 'ios',
      label: 'iOS',
      options: entries.filter((x) => x.value.startsWith('ios_')),
    },
  ]
})

function normalizeSelectedProjects(projects) {
  return Array.isArray(projects) ? projects.filter(Boolean) : []
}

const selectedProjects = computed(() => normalizeSelectedProjects(st.select_projects))

const currentProjectPlatform = computed(() => {
  const list = selectedProjects.value
  if (!list.length) return 'none'
  const allIos = list.every((p) => String(p).startsWith('ios_'))
  const allGp = list.every((p) => !String(p).startsWith('ios_'))
  if (allIos) return 'ios'
  if (allGp) return 'gp'
  return 'multi'
})

const projectPlatformTagText = computed(() => {
  const p = currentProjectPlatform.value
  if (p === 'none') return '未选'
  if (p === 'ios') return 'iOS'
  if (p === 'gp') return 'GP'
  return '多项目'
})

function projectDisplayName(projectKey) {
  return COMPARE_PROJECT_LABEL_BY_NAME[projectKey] || projectKey
}

function encodeSchemeValue(project, schemeName) {
  return `${project}${SCHEME_VALUE_SEP}${schemeName}`
}

function parseSchemeValue(value) {
  const s = String(value || '')
  const idx = s.indexOf(SCHEME_VALUE_SEP)
  if (idx < 0) {
    return { project: selectedProjects.value[0] || '', schemeName: s }
  }
  return { project: s.slice(0, idx), schemeName: s.slice(idx + SCHEME_VALUE_SEP.length) }
}

function schemeOptionLabel(project, schemeName) {
  const projects = selectedProjects.value
  if (projects.length <= 1) return schemeName
  return `[${projectDisplayName(project)}] ${schemeName}`
}

function buildSchemeEntries(projects, nameLists) {
  const merged = []
  const seen = new Set()
  projects.forEach((project, idx) => {
    const names = nameLists[idx] || []
    for (const name of names) {
      const value = encodeSchemeValue(project, name)
      if (seen.has(value)) continue
      seen.add(value)
      merged.push({
        project,
        schemeName: name,
        value,
        label: schemeOptionLabel(project, name),
      })
    }
  })
  return merged
}

/** 将接口 adwaynum_files 规范为字符串列表，保持原顺序 */
function normalizeAdwaynumFileList(raw) {
  if (!Array.isArray(raw)) return []
  return raw
    .map((x) => {
      if (typeof x === 'string') return x
      if (x == null) return ''
      return String(x)
    })
    .filter((s) => s.length > 0)
}

function schemeEntrySearchHaystack(item) {
  return [
    item.schemeName,
    item.label,
    item.project,
    projectDisplayName(item.project),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

function schemeEntryMatchesQuery(item, query) {
  const q = (query || '').trim().toLowerCase()
  if (!q) return true
  return schemeEntrySearchHaystack(item).includes(q)
}

function filterAndCapSchemeEntries(entries, query) {
  const list = Array.isArray(entries) ? entries : []
  const filtered = list.filter((item) => schemeEntryMatchesQuery(item, query))
  return filtered.slice(0, SCHEME_DROPDOWN_CAP)
}

/** 下拉选项：有搜索词时仅展示匹配项，避免把上次已选方案顶回列表 */
function buildSchemeOptionsForSelect(entries, filterQuery, selectedValue) {
  const q = (filterQuery || '').trim()
  let options = filterAndCapSchemeEntries(entries, filterQuery)
  if (!q && selectedValue && !options.some((x) => x.value === selectedValue)) {
    const hit = entries.find((x) => x.value === selectedValue)
    if (hit) options = [hit, ...options].slice(0, SCHEME_DROPDOWN_CAP)
  }
  return options
}

const leftSchemeOptionsForSelect = computed(() =>
  buildSchemeOptionsForSelect(
    st.left_scheme_entries,
    st.left_scheme_filter_query,
    st.select_left_Adwaynum
  )
)

const rightSchemeOptionsForSelect = computed(() =>
  buildSchemeOptionsForSelect(
    st.right_scheme_entries,
    st.right_scheme_filter_query,
    st.select_right_Adwaynum
  )
)

function onLeftSchemeFilter(query) {
  st.left_scheme_filter_query = String(query ?? '')
}

function onRightSchemeFilter(query) {
  st.right_scheme_filter_query = String(query ?? '')
}

function onLeftSchemeSelectVisible(visible) {
  if (!visible) st.left_scheme_filter_query = ''
}

function onRightSchemeSelectVisible(visible) {
  if (!visible) st.right_scheme_filter_query = ''
}

function apiErr(res) {
  return res?.msg || res?.message || '未知错误'
}

/** 与后端 git_config_views._parse_time_slot_slot 一致：left_time_slot_2 / right_time_slot_2 → 2 */
function parseCompareSlot(timeslot) {
  const parts = String(timeslot ?? '').split('_')
  if (parts.length >= 4) {
    const n = parseInt(parts[3], 10)
    return Number.isNaN(n) ? 0 : n
  }
  return 0
}

function pruneSchemeSelection(side) {
  const selected = side === 'left' ? st.select_left_Adwaynum : st.select_right_Adwaynum
  if (!selected) return
  const entries = side === 'left' ? st.left_scheme_entries : st.right_scheme_entries
  if (!entries.some((x) => x.value === selected)) {
    if (side === 'left') {
      st.select_left_Adwaynum = ''
      st.renderedLeftJson = ''
      st.api_left_region_map = {}
    } else {
      st.select_right_Adwaynum = ''
      st.renderedRightJson = ''
      st.api_right_region_map = {}
    }
  }
}

async function fetchMergedSchemeEntries(projects, timeslot) {
  const normalized = normalizeSelectedProjects(projects)
  if (!normalized.length) return []
  const lists = await Promise.all(
    normalized.map((project) => fetchAdwaynumFileList(project, timeslot))
  )
  return buildSchemeEntries(normalized, lists)
}

function onProjectsChange() {
  st.select_projects = normalizeSelectedProjects(st.select_projects)
  fetchGitInfo()
}

async function reloadSchemeEntries() {
  const projects = selectedProjects.value
  if (!projects.length) return
  const sameSlot = parseCompareSlot(st.leftTimeslot) === parseCompareSlot(st.rightTimeslot)
  if (sameSlot) {
    const entries = await fetchMergedSchemeEntries(projects, st.leftTimeslot)
    st.left_scheme_entries = entries
    st.right_scheme_entries = entries
  } else {
    await reloadLeftFiles()
    await reloadRightFiles()
  }
  pruneSchemeSelection('left')
  pruneSchemeSelection('right')
}

async function onSyncAdwaynumCache() {
  const projects = selectedProjects.value
  if (!projects.length) {
    ElMessage.warning('请先选择至少一个项目')
    return
  }
  loading.files = true
  adwaynumFileCache.clear()
  try {
    const res = await rebuild_adwaynum_cache(projects)
    if (!res?.success) {
      ElMessage.error(apiErr(res))
      return
    }
    await reloadSchemeEntries()
    ElMessage.success(res.message || res.msg || '缓存同步完成')
  } catch (e) {
    ElMessage.error('同步缓存失败：' + (e.message || String(e)))
  } finally {
    loading.files = false
  }
}

function applyBatchModeLocks() {
  st.is_show_discrepancy = 'is_show_diff'
  st.result_render_style = 'text_view'
  st.left_region = 'all'
  st.right_region = 'all'
}

function onCompareModeChange() {
  if (st.compare_mode === 'batch') {
    st._single_discrepancy_backup = st.is_show_discrepancy
    st._single_render_style_backup = st.result_render_style
    applyBatchModeLocks()
    st.renderedLeftJson = ''
    st.renderedRightJson = ''
    return
  }
  if (st._single_discrepancy_backup) {
    st.is_show_discrepancy = st._single_discrepancy_backup
  }
  if (st._single_render_style_backup) {
    st.result_render_style = st._single_render_style_backup
  }
  st.renderedLeftJson = ''
  st.renderedRightJson = ''
}

function onDisplayModeChange() {
  if (isBatchMode.value) return
  runCompare()
}

/** 解析批量粘贴的方案号：空格、换行、逗号等分隔 */
function parseBatchSchemeInput(text) {
  return String(text || '')
    .split(/[\s,，;；\n\r\t]+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

/**
 * 在已选项目的方案目录中解析方案号（精确匹配优先，否则唯一模糊匹配）
 */
function resolveBatchSchemeToken(token, entries) {
  const t = String(token || '').trim().toLowerCase()
  if (!t) return null
  const list = Array.isArray(entries) ? entries : []

  const exact = list.filter((e) => e.schemeName.toLowerCase() === t)
  if (exact.length === 1) return exact[0]
  if (exact.length > 1) {
    return { ambiguous: true, matches: exact, token }
  }

  const fuzzy = list.filter((e) => e.schemeName.toLowerCase().includes(t))
  if (fuzzy.length === 1) return fuzzy[0]
  if (fuzzy.length > 1) {
    fuzzy.sort((a, b) => a.schemeName.length - b.schemeName.length)
    return { ambiguous: true, matches: fuzzy, token }
  }
  return null
}

function resolveBatchSchemeList(tokens, entries, sideLabel) {
  const resolved = []
  const unresolved = []
  const ambiguous = []

  for (const token of tokens) {
    const hit = resolveBatchSchemeToken(token, entries)
    if (!hit) {
      unresolved.push(token)
      continue
    }
    if (hit.ambiguous) {
      ambiguous.push(hit)
      resolved.push(hit.matches[0])
      continue
    }
    resolved.push(hit)
  }
  return { resolved, unresolved, ambiguous, sideLabel }
}

async function ensureSchemeEntriesForTimeslot(timeslot) {
  const slotNum = parseCompareSlot(timeslot)
  const sameSlot =
    parseCompareSlot(st.leftTimeslot) === parseCompareSlot(st.rightTimeslot)
  if (sameSlot && st.left_scheme_entries.length) {
    return st.left_scheme_entries
  }
  if (timeslot === st.leftTimeslot && st.left_scheme_entries.length) {
    return st.left_scheme_entries
  }
  if (timeslot === st.rightTimeslot && st.right_scheme_entries.length) {
    return st.right_scheme_entries
  }
  return fetchMergedSchemeEntries(selectedProjects.value, timeslot)
}

async function fetchAdwaynumJson(project, schemeName, timeslot) {
  const res = await get_adwaynum_json_2(project, '', schemeName, timeslot)
  if (res?.success) {
    return res.data?.adwaynum_json || {}
  }
  throw new Error(apiErr(res))
}

async function fetchRegionMapForScheme(project, schemeName, timeslot) {
  return fetchAdwaynumJson(project, schemeName, timeslot)
}

function batchPairBanner(index, total, entry) {
  const label = entry?.label || entry?.schemeName || '—'
  return `=============【${index + 1}/${total}】${label}=============`
}

async function runBatchCompare() {
  applyBatchModeLocks()

  if (!selectedProjects.value.length) {
    ElMessage.warning('请先选择至少一个项目')
    return
  }

  const leftTokens = parseBatchSchemeInput(st.batch_left_input)
  const rightTokens = parseBatchSchemeInput(st.batch_right_input)
  if (!leftTokens.length || !rightTokens.length) {
    ElMessage.warning('请分别在左右两侧粘贴至少一个方案号')
    return
  }

  loading.compare = true
  st.renderedLeftJson = ''
  st.renderedRightJson = ''

  try {
    const [leftCatalog, rightCatalog] = await Promise.all([
      ensureSchemeEntriesForTimeslot(st.leftTimeslot),
      ensureSchemeEntriesForTimeslot(st.rightTimeslot),
    ])

    const leftRes = resolveBatchSchemeList(leftTokens, leftCatalog, '左侧')
    const rightRes = resolveBatchSchemeList(rightTokens, rightCatalog, '右侧')

    if (leftRes.unresolved.length) {
      ElMessage.error(`左侧未匹配方案：${leftRes.unresolved.join('、')}`)
      return
    }
    if (rightRes.unresolved.length) {
      ElMessage.error(`右侧未匹配方案：${rightRes.unresolved.join('、')}`)
      return
    }
    if (leftRes.ambiguous.length || rightRes.ambiguous.length) {
      const parts = []
      if (leftRes.ambiguous.length) {
        parts.push(`左侧「${leftRes.ambiguous.map((x) => x.token).join('、')}」存在多个匹配，已取最短方案名`)
      }
      if (rightRes.ambiguous.length) {
        parts.push(`右侧「${rightRes.ambiguous.map((x) => x.token).join('、')}」存在多个匹配，已取最短方案名`)
      }
      ElMessage.warning(parts.join('；'))
    }

    const pairCount = Math.min(leftRes.resolved.length, rightRes.resolved.length)
    if (pairCount === 0) {
      ElMessage.warning('没有可配对的方案')
      return
    }
    if (leftRes.resolved.length !== rightRes.resolved.length) {
      ElMessage.warning(
        `左右方案数量不一致（左 ${leftRes.resolved.length} / 右 ${rightRes.resolved.length}），仅比对前 ${pairCount} 对`
      )
    }

    let leftHtml = ''
    let rightHtml = ''
    let hasAnyDiff = false

    for (let i = 0; i < pairCount; i += 1) {
      const L = leftRes.resolved[i]
      const R = rightRes.resolved[i]
      const leftBanner = batchPairBanner(i, pairCount, L)
      const rightBanner = batchPairBanner(i, pairCount, R)
      try {
        const [leftMap, rightMap] = await Promise.all([
          fetchRegionMapForScheme(L.project, L.schemeName, st.leftTimeslot),
          fetchRegionMapForScheme(R.project, R.schemeName, st.rightTimeslot),
        ])
        let { left, right } = pickJsonRegions(leftMap, rightMap, 0)
        ;({ left, right } = filterDiffDataPaired(left, right))
        if ((left && left.trim()) || (right && right.trim())) {
          hasAnyDiff = true
        }
        leftHtml += `${leftBanner}<br/>${left || '<span class="diff-same">（无差异项）</span>'}<br/><br/>`
        rightHtml += `${rightBanner}<br/>${right || '<span class="diff-same">（无差异项）</span>'}<br/><br/>`
      } catch (e) {
        const errMsg = escapeHtml(e.message || String(e))
        leftHtml += `${leftBanner}<br/><span class="diff-missing">加载或比对失败：${errMsg}</span><br/><br/>`
        rightHtml += `${rightBanner}<br/><span class="diff-missing">加载或比对失败：${errMsg}</span><br/><br/>`
      }
    }

    st.renderedLeftJson = wrapTextAsStructuredHtml(leftHtml.trim())
    st.renderedRightJson = wrapTextAsStructuredHtml(rightHtml.trim())

    if (!hasAnyDiff) {
      ElMessage.info('批量比对完成：各对方案均无差异项')
    } else {
      ElMessage.success(`批量比对完成，共 ${pairCount} 对`)
    }

    const statisticStr = `project_name=${selectedProjects.value.join(',')}
&batch_compare=1
&left_count=${leftRes.resolved.length}
&right_count=${rightRes.resolved.length}
&pair_count=${pairCount}
&user_name=${getUserCnName()}
`
    report_statistic_info(statisticStr).catch(() => {})
  } catch (e) {
    ElMessage.error('批量比对失败：' + (e.message || String(e)))
  } finally {
    loading.compare = false
  }
}

/** 切换项目或进入页面：拉取已选项目合并后的方案列表 */
async function fetchGitInfo() {
  await nextTick()
  st.select_projects = normalizeSelectedProjects(st.select_projects)
  adwaynumFileCache.clear()
  st.select_left_Adwaynum = ''
  st.select_right_Adwaynum = ''
  st.renderedLeftJson = ''
  st.renderedRightJson = ''
  st.left_scheme_entries = []
  st.right_scheme_entries = []
  st.left_scheme_filter_query = ''
  st.right_scheme_filter_query = ''
  st.api_left_region_map = {}
  st.api_right_region_map = {}

  const projects = selectedProjects.value
  if (!projects.length) {
    return
  }

  loading.files = true
  try {
    const sameSlot = parseCompareSlot(st.leftTimeslot) === parseCompareSlot(st.rightTimeslot)
    if (sameSlot) {
      const entries = await fetchMergedSchemeEntries(projects, st.leftTimeslot)
      st.left_scheme_entries = entries
      st.right_scheme_entries = entries
    } else {
      await reloadLeftFiles()
      await reloadRightFiles()
    }
  } catch (e) {
    ElMessage.error('请求失败：' + (e.message || String(e)))
  } finally {
    loading.files = false
  }
}

async function reloadLeftFiles() {
  st.renderedLeftJson = ''
  st.api_left_region_map = {}
  st.left_scheme_filter_query = ''
  const entries = await fetchMergedSchemeEntries(selectedProjects.value, st.leftTimeslot)
  st.left_scheme_entries = entries
  pruneSchemeSelection('left')
}

async function reloadRightFiles() {
  st.renderedRightJson = ''
  st.api_right_region_map = {}
  st.right_scheme_filter_query = ''
  const entries = await fetchMergedSchemeEntries(selectedProjects.value, st.rightTimeslot)
  st.right_scheme_entries = entries
  pruneSchemeSelection('right')
}

async function onLeftSlotChange() {
  loading.files = true
  try {
    await reloadLeftFiles()
    if (parseCompareSlot(st.leftTimeslot) === parseCompareSlot(st.rightTimeslot)) {
      st.right_scheme_entries = [...st.left_scheme_entries]
      st.right_scheme_filter_query = ''
      pruneSchemeSelection('right')
    }
  } catch (e) {
    ElMessage.error('请求失败：' + (e.message || String(e)))
  } finally {
    loading.files = false
  }
}
async function onRightSlotChange() {
  loading.files = true
  try {
    await reloadRightFiles()
    if (parseCompareSlot(st.leftTimeslot) === parseCompareSlot(st.rightTimeslot)) {
      st.left_scheme_entries = [...st.right_scheme_entries]
      st.left_scheme_filter_query = ''
      pruneSchemeSelection('left')
    }
  } catch (e) {
    ElMessage.error('请求失败：' + (e.message || String(e)))
  } finally {
    loading.files = false
  }
}

async function fetchAdwaynumFileList(project_name, timeslot) {
  const slotNum = parseCompareSlot(timeslot)
  const cacheKey = `${project_name}::slot_${slotNum}`
  const cached = adwaynumFileCache.get(cacheKey)
  if (cached) return cached
  try {
    const res = await get_adwaynum_file(project_name, '', timeslot)
    if (res?.success) {
      const list = normalizeAdwaynumFileList(res.data?.adwaynum_files)
      adwaynumFileCache.set(cacheKey, list)
      return list
    }
    ElMessage.error('获取方案列表失败：' + apiErr(res))
    return []
  } catch (e) {
    ElMessage.error('获取方案列表失败：' + (e.message || String(e)))
    return []
  }
}

async function getLeftadwaynumJson() {
  if (!st.select_left_Adwaynum) return
  const { project, schemeName } = parseSchemeValue(st.select_left_Adwaynum)
  loading.json = true
  try {
    st.api_left_region_map = await fetchAdwaynumJson(project, schemeName, st.leftTimeslot)
    const first = Object.keys(st.api_left_region_map)[0]
    if (first) st.left_region = first
    runCompare()
  } catch (e) {
    ElMessage.error('获取左侧 JSON 失败：' + (e.message || String(e)))
  } finally {
    loading.json = false
  }
}

async function getRightadwaynumJson() {
  if (!st.select_right_Adwaynum) return
  const { project, schemeName } = parseSchemeValue(st.select_right_Adwaynum)
  loading.json = true
  try {
    st.api_right_region_map = await fetchAdwaynumJson(project, schemeName, st.rightTimeslot)
    const first = Object.keys(st.api_right_region_map)[0]
    if (first) st.right_region = first
    runCompare()
  } catch (e) {
    ElMessage.error('获取右侧 JSON 失败：' + (e.message || String(e)))
  } finally {
    loading.json = false
  }
}

function sendStatistic() {
  const statisticStr = `project_name=${selectedProjects.value.join(',')}
&left_Adwaynum=${st.select_left_Adwaynum}
&right_Adwaynum=${st.select_right_Adwaynum}
&leftTimeslot=${st.leftTimeslot}
&rightTimeslot=${st.rightTimeslot}
&left_region=${st.left_region}
&right_region=${st.right_region}
&user_name=${getUserCnName()}
`
  report_statistic_info(statisticStr).catch(() => {})
}

function prettyJson(data) {
  try {
    return JSON.stringify(data ?? {}, null, 2)
  } catch {
    return JSON.stringify({ error: 'JSON 序列化失败' }, null, 2)
  }
}

/** 按深度生成缩进空格（每层 2 空格） */
function indentStr(depth) {
  return '  '.repeat(Math.max(0, depth))
}

/**
 * 递归排序对象 key，确保 JSON.stringify 输出一致的 key 顺序，
 * 避免因后端返回 dict key 顺序不同导致 diffLines 错位。
 * 数组元素若是对象也会递归排序；非对象/非 null 原样返回。
 */
function sortObjectKeysRecursively(obj) {
  if (obj == null || typeof obj !== 'object') return obj
  if (Array.isArray(obj)) {
    return obj.map(sortObjectKeysRecursively)
  }
  const sorted = {}
  const keys = Object.keys(obj).sort()
  for (const k of keys) {
    sorted[k] = sortObjectKeysRecursively(obj[k])
  }
  return sorted
}

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

/** jsdiff 的片段拆成不带换行符的行列表 */
function splitDiffValueToLines(value) {
  if (value === '' || value == null) return []
  const lines = String(value).split(/\r?\n/)
  if (lines.length && lines[lines.length - 1] === '') lines.pop()
  return lines
}

/** 单侧行列表 → HTML */
function renderJsonDiffSide(rows) {
  return rows
    .map((row) => {
      const line = escapeHtml(row.text)
      return `<div class="diff-json-line diff-json-line-${row.type}"><span class="diff-json-sign">${row.sign}</span><span class="diff-json-text">${line || '&nbsp;'}</span></div>`
    })
    .join('')
}

/**
 * 从 pretty 打印的一行 JSON 中取 object 的 key（`"key":` 形式）；数组行、括号行等返回 null。
 */
function extractJsonObjectKeyHint(line) {
  const m = String(line).match(/"((?:[^"\\]|\\.)*)"\s*:/)
  return m ? m[1] : null
}

/**
 * 将一段连续 del + 一段连续 add 按「同一 object 键」对齐为 chg（左右同行、仅颜色区分），
 * 解决同 key 仅值变化却上下错位、以及一侧多出新 key 行时 del/add 行数不一致的问题。
 * 按 del 行原始顺序输出，避免将后方匹配行提前到删除块之前（破坏 JSON 结构位置）。
 * @param {{text:string}[]} delRows
 * @param {{text:string}[]} addRows
 * @returns {{kind:'chg'|'del'|'add', left?: string, right?: string}[]}
 */
function buildKeyAlignedDelAddPairs(delRows, addRows) {
  const delTexts = delRows.map((r) => r.text)
  const addTexts = addRows.map((r) => r.text)
  const nA = addTexts.length
  const addUsed = new Array(nA).fill(false)
  const out = []
  let addSearchStart = 0

  function findAddForKey(key) {
    for (let j = addSearchStart; j < nA; j += 1) {
      if (addUsed[j]) continue
      if (extractJsonObjectKeyHint(addTexts[j]) === key) return j
    }
    for (let j = 0; j < addSearchStart; j += 1) {
      if (addUsed[j]) continue
      if (extractJsonObjectKeyHint(addTexts[j]) === key) return j
    }
    return -1
  }

  for (let di = 0; di < delTexts.length; di += 1) {
    const dl = delTexts[di]
    const k = extractJsonObjectKeyHint(dl)
    if (k) {
      const aj = findAddForKey(k)
      if (aj >= 0) {
        addUsed[aj] = true
        addSearchStart = aj + 1
        out.push({ kind: 'chg', left: dl, right: addTexts[aj] })
        continue
      }
    }
    out.push({ kind: 'del', left: dl })
  }
  for (let aj = 0; aj < nA; aj += 1) {
    if (!addUsed[aj]) out.push({ kind: 'add', right: addTexts[aj] })
  }
  return out
}

/** 从一组 diff 行中提取第一个「对象 key」（如 "fail_factor": { → "fail_factor"），没有则返回 null */
function firstStructuralObjectKey(rows) {
  for (const r of rows) {
    const t = (r.text || '').trim()
    const m = t.match(/^"((?:[^"\\]|\\.)*)"\s*:\s*\{/)
    if (m) return m[1]
  }
  return null
}

/**
 * 将「连续 del + 连续 add」合并：仅当 key 一致时对齐为 chg，避免层级错位时误合并。
 * 额外检查 del / add 两个块是否是同一「对象」（首行 "key": { 相同或至少一侧无结构 key），
 * 防止左侧 fail_factor 的 del 块与右侧 fail_factor2 的 add 块被错误合并。
 */
function mergeSameKeyValueDiffRows(leftOut, rightOut) {
  const n = leftOut.length
  if (n !== rightOut.length) return { leftOut, rightOut }
  const outL = []
  const outR = []
  let i = 0
  while (i < n) {
    const rowL = leftOut[i]
    if (rowL.type === 'section' || rowL.type === 'section-spacer') {
      outL.push(rowL)
      outR.push(rightOut[i])
      i += 1
      continue
    }
    if (rowL.type === 'del' && rightOut[i].type === 'blank') {
      let s = i
      while (s < n && leftOut[s].type === 'del' && rightOut[s].type === 'blank') s += 1
      const delEnd = s
      if (delEnd < n && leftOut[delEnd].type === 'blank' && rightOut[delEnd].type === 'add') {
        let t = delEnd
        while (t < n && leftOut[t].type === 'blank' && rightOut[t].type === 'add') t += 1
        const delLen = delEnd - i
        const addLen = t - delEnd
        if (delLen > 0 && addLen > 0) {
          const delRows = leftOut.slice(i, delEnd)
          const addRows = rightOut.slice(delEnd, t)
          // 检查两个块是否来自不同的「对象」（如左侧 fail_factor vs 右侧 fail_factor2），
          // 若是则跳过合并，避免内部同名 key 被错误配对（如 left.fail_factor.retry_count 配对 right.fail_factor2.retry_count）
          const delObjKey = firstStructuralObjectKey(delRows)
          const addObjKey = firstStructuralObjectKey(addRows)
          const sameObject = !delObjKey || !addObjKey || delObjKey === addObjKey
          if (sameObject) {
            const pairs = buildKeyAlignedDelAddPairs(delRows, addRows)
            for (const p of pairs) {
              if (p.kind === 'chg') {
                outL.push({ type: 'chg', text: p.left, sign: '' })
                outR.push({ type: 'chg', text: p.right, sign: '' })
              } else if (p.kind === 'del') {
                outL.push({ type: 'del', text: p.left, sign: '-' })
                outR.push({ type: 'blank', text: '', sign: ' ' })
              } else {
                outL.push({ type: 'blank', text: '', sign: ' ' })
                outR.push({ type: 'add', text: p.right, sign: '+' })
              }
            }
          } else {
            // 不同对象 — 保持原始 del / add，不合并
            for (const dr of delRows) {
              outL.push({ type: 'del', text: dr.text, sign: '-' })
              outR.push({ type: 'blank', text: '', sign: ' ' })
            }
            for (const ar of addRows) {
              outL.push({ type: 'blank', text: '', sign: ' ' })
              outR.push({ type: 'add', text: ar.text, sign: '+' })
            }
          }
          i = t
          continue
        }
      }
    }
    outL.push(leftOut[i])
    outR.push(rightOut[i])
    i += 1
  }
  return { leftOut: outL, rightOut: outR }
}

/**
 * 使用结构化递归对比替代纯文本 diffLines。
 *
 * 根本问题：diffLines 是文本行级 diff，不理解 JSON 的结构。
 * 当左侧 fail_factor 的值恰好与右侧 fail_factor2 的值相同时，
 * Myers diff 会优先对齐"内容相同"的行，导致左侧 fail_factor 与右侧 fail_factor2 错位对比。
 *
 * 改为按 JSON key 递归对比：同一层级的每个 key 只与同名的 key 对比，
 * 杜绝跨 key 的错误对齐。
 *
 * @returns {{ leftOut: {type:string,text:string,sign:string}[], rightOut: same }}
 */
function buildJsonDiffRows(leftData, rightData, depth = 0) {
  const leftSorted = sortObjectKeysRecursively(leftData)
  const rightSorted = sortObjectKeysRecursively(rightData)

  let result
  if (isPlainObject(leftSorted) && isPlainObject(rightSorted)) {
    result = buildObjectDiffRows(leftSorted, rightSorted, depth)
  } else if (Array.isArray(leftSorted) && Array.isArray(rightSorted)) {
    result = buildArrayDiffRows(leftSorted, rightSorted, depth)
  } else {
    result = buildTextDiffRows(leftSorted, rightSorted, depth)
  }

  // 合并相邻的 del+add 对（同 key 值变更 → chg 黄色高亮）
  const merged = mergeSameKeyValueDiffRows(result.leftOut, result.rightOut)

  // 修复跨侧 key 差异导致的悬空尾逗号：
  // 当一侧有 key 而另一侧无时，allKeys（并集）会使 isLast 判定错误，
  // 导致前一个 key 的闭合 } 被错误追加逗号。在所有深度统一清理。
  fixTrailingCommas(merged.leftOut)
  fixTrailingCommas(merged.rightOut)

  return merged
}

function isPlainObject(val) {
  return val !== null && typeof val === 'object' && !Array.isArray(val)
}

/**
 * 对象级别结构化对比：每个 key 只与同名的 key 对比
 */
function buildObjectDiffRows(leftObj, rightObj, depth = 0) {
  const indent = indentStr(depth)
  const innerIndent = indentStr(depth + 1)
  const allKeys = [...new Set([...Object.keys(leftObj), ...Object.keys(rightObj)])].sort()
  const leftOut = [{ type: 'same', text: indent + '{', sign: ' ' }]
  const rightOut = [{ type: 'same', text: indent + '{', sign: ' ' }]

  for (let i = 0; i < allKeys.length; i++) {
    const key = allKeys[i]
    const isLast = i === allKeys.length - 1
    const hasL = key in leftObj
    const hasR = key in rightObj

    if (hasL && hasR) {
      // 两侧都有该 key → 结构化递归对比值
      const sub = buildJsonDiffRows(leftObj[key], rightObj[key], depth + 1)
      // 注入 key 行（"key": 开头），替换子结果第一行的缩进前缀
      const keyLine = `${innerIndent}"${key}": `
      if (sub.leftOut.length > 0 && sub.rightOut.length > 0) {
        // 找到每侧第一个非 blank 行注入 key（修复：当值不同时 buildTextDiffRows 会在首行放置 blank，
        // 若盲目注入 sub.leftOut[0]/sub.rightOut[0] 会把 key 写入空白行，导致右侧 add 行无 key 名称）
        const leftFirstIdx = sub.leftOut.findIndex(r => r.type !== 'blank')
        const rightFirstIdx = sub.rightOut.findIndex(r => r.type !== 'blank')
        if (leftFirstIdx >= 0) {
          const leftFirst = sub.leftOut[leftFirstIdx].text
          sub.leftOut[leftFirstIdx] = { ...sub.leftOut[leftFirstIdx], text: keyLine + (leftFirst.startsWith(innerIndent) ? leftFirst.slice(innerIndent.length) : leftFirst) }
        }
        if (rightFirstIdx >= 0) {
          const rightFirst = sub.rightOut[rightFirstIdx].text
          sub.rightOut[rightFirstIdx] = { ...sub.rightOut[rightFirstIdx], text: keyLine + (rightFirst.startsWith(innerIndent) ? rightFirst.slice(innerIndent.length) : rightFirst) }
        }
      } else if (sub.leftOut.length > 0) {
        const leftFirstIdx = sub.leftOut.findIndex(r => r.type !== 'blank')
        if (leftFirstIdx >= 0) {
          const leftFirst = sub.leftOut[leftFirstIdx].text
          sub.leftOut[leftFirstIdx] = { ...sub.leftOut[leftFirstIdx], text: keyLine + (leftFirst.startsWith(innerIndent) ? leftFirst.slice(innerIndent.length) : leftFirst) }
        }
      } else if (sub.rightOut.length > 0) {
        const rightFirstIdx = sub.rightOut.findIndex(r => r.type !== 'blank')
        if (rightFirstIdx >= 0) {
          const rightFirst = sub.rightOut[rightFirstIdx].text
          sub.rightOut[rightFirstIdx] = { ...sub.rightOut[rightFirstIdx], text: keyLine + (rightFirst.startsWith(innerIndent) ? rightFirst.slice(innerIndent.length) : rightFirst) }
        }
      } else {
        sub.leftOut.push({ type: 'same', text: keyLine, sign: ' ' })
        sub.rightOut.push({ type: 'same', text: keyLine, sign: ' ' })
      }
      // 在最后一个非 blank 行追加逗号（如果不是最后一个 key）
      if (!isLast && sub.leftOut.length > 0) {
        let lastL = sub.leftOut.length - 1
        while (lastL >= 0 && sub.leftOut[lastL].type === 'blank') lastL--
        if (lastL >= 0) {
          sub.leftOut[lastL] = { ...sub.leftOut[lastL], text: sub.leftOut[lastL].text + ',' }
        }
      }
      if (!isLast && sub.rightOut.length > 0) {
        let lastR = sub.rightOut.length - 1
        while (lastR >= 0 && sub.rightOut[lastR].type === 'blank') lastR--
        if (lastR >= 0) {
          sub.rightOut[lastR] = { ...sub.rightOut[lastR], text: sub.rightOut[lastR].text + ',' }
        }
      }
      leftOut.push(...sub.leftOut)
      rightOut.push(...sub.rightOut)
    } else if (hasL) {
      // 仅左侧有 → 整个值标记为 del
      const lines = prettyJson(leftObj[key]).split(/\r?\n/)
      const firstLine = `${innerIndent}"${key}": ${lines[0] || 'null'}`
      // 多行值（对象/数组）的逗号应放在最后一行，而非第一行开括号
      const firstComma = (lines.length === 1 && !isLast) ? ',' : ''
      leftOut.push({ type: 'del', text: firstLine + firstComma, sign: '-' })
      rightOut.push({ type: 'blank', text: '', sign: ' ' })
      for (let j = 1; j < lines.length; j++) {
        const comma = (j === lines.length - 1 && !isLast) ? ',' : ''
        leftOut.push({ type: 'del', text: innerIndent + lines[j] + comma, sign: '-' })
        rightOut.push({ type: 'blank', text: '', sign: ' ' })
      }
    } else {
      // 仅右侧有 → 整个值标记为 add
      const lines = prettyJson(rightObj[key]).split(/\r?\n/)
      const firstLine = `${innerIndent}"${key}": ${lines[0] || 'null'}`
      const firstComma = (lines.length === 1 && !isLast) ? ',' : ''
      leftOut.push({ type: 'blank', text: '', sign: ' ' })
      rightOut.push({ type: 'add', text: firstLine + firstComma, sign: '+' })
      for (let j = 1; j < lines.length; j++) {
        const comma = (j === lines.length - 1 && !isLast) ? ',' : ''
        leftOut.push({ type: 'blank', text: '', sign: ' ' })
        rightOut.push({ type: 'add', text: innerIndent + lines[j] + comma, sign: '+' })
      }
    }
  }

  leftOut.push({ type: 'same', text: indent + '}', sign: ' ' })
  rightOut.push({ type: 'same', text: indent + '}', sign: ' ' })

  return { leftOut, rightOut }
}

/**
 * 数组级别结构化对比：按索引逐一对比
 */
function buildArrayDiffRows(leftArr, rightArr, depth = 0) {
  const indent = indentStr(depth)
  const innerIndent = indentStr(depth + 1)
  const maxLen = Math.max(leftArr.length, rightArr.length)
  const leftOut = [{ type: 'same', text: indent + '[', sign: ' ' }]
  const rightOut = [{ type: 'same', text: indent + '[', sign: ' ' }]

  for (let i = 0; i < maxLen; i++) {
    const isLast = i === maxLen - 1
    const hasL = i < leftArr.length
    const hasR = i < rightArr.length

    if (hasL && hasR) {
      const sub = buildJsonDiffRows(leftArr[i], rightArr[i], depth + 1)
      if (!isLast) {
        if (sub.leftOut.length > 0) {
          let li = sub.leftOut.length - 1
          while (li >= 0 && sub.leftOut[li].type === 'blank') li--
          if (li >= 0) {
            sub.leftOut[li] = { ...sub.leftOut[li], text: sub.leftOut[li].text + ',' }
          }
        }
        if (sub.rightOut.length > 0) {
          let ri = sub.rightOut.length - 1
          while (ri >= 0 && sub.rightOut[ri].type === 'blank') ri--
          if (ri >= 0) {
            sub.rightOut[ri] = { ...sub.rightOut[ri], text: sub.rightOut[ri].text + ',' }
          }
        }
      }
      // 确保两侧行数一致
      const maxSub = Math.max(sub.leftOut.length, sub.rightOut.length)
      for (let j = 0; j < maxSub; j++) {
        const lr = sub.leftOut[j]
        const rr = sub.rightOut[j]
        if (lr && rr) {
          leftOut.push(lr)
          rightOut.push(rr)
        } else if (lr) {
          leftOut.push(lr)
          rightOut.push({ type: 'blank', text: '', sign: ' ' })
        } else {
          leftOut.push({ type: 'blank', text: '', sign: ' ' })
          rightOut.push(rr)
        }
      }
    } else if (hasL) {
      const lines = prettyJson(leftArr[i]).split(/\r?\n/)
      for (let j = 0; j < lines.length; j++) {
        const comma = (j === lines.length - 1 && !isLast) ? ',' : ''
        leftOut.push({ type: 'del', text: innerIndent + lines[j] + comma, sign: '-' })
        rightOut.push({ type: 'blank', text: '', sign: ' ' })
      }
    } else {
      const lines = prettyJson(rightArr[i]).split(/\r?\n/)
      for (let j = 0; j < lines.length; j++) {
        const comma = (j === lines.length - 1 && !isLast) ? ',' : ''
        leftOut.push({ type: 'blank', text: '', sign: ' ' })
        rightOut.push({ type: 'add', text: innerIndent + lines[j] + comma, sign: '+' })
      }
    }
  }

  leftOut.push({ type: 'same', text: indent + ']', sign: ' ' })
  rightOut.push({ type: 'same', text: indent + ']', sign: ' ' })

  return { leftOut, rightOut }
}

/**
 * 非对象/非数组值的对比：回退到 diffLines
 */
function buildTextDiffRows(leftVal, rightVal, depth = 0) {
  const indent = indentStr(depth)
  const leftStr = prettyJson(leftVal)
  const rightStr = prettyJson(rightVal)
  const parts = diffLines(leftStr, rightStr)

  const leftOut = []
  const rightOut = []

  for (const part of parts) {
    const lines = splitDiffValueToLines(part.value)
    if (part.removed) {
      for (const line of lines) {
        leftOut.push({ type: 'del', text: indent + line, sign: '-' })
        rightOut.push({ type: 'blank', text: '', sign: ' ' })
      }
    } else if (part.added) {
      for (const line of lines) {
        leftOut.push({ type: 'blank', text: '', sign: ' ' })
        rightOut.push({ type: 'add', text: indent + line, sign: '+' })
      }
    } else {
      for (const line of lines) {
        leftOut.push({ type: 'same', text: indent + line, sign: ' ' })
        rightOut.push({ type: 'same', text: indent + line, sign: ' ' })
      }
    }
  }

  return { leftOut, rightOut }
}

/* ---- 原 buildJsonDiffRows（已替换为上述结构化版本）---- */

/** 按「区域标题 + 正文」分段（全部模式）；单区域时为整段 [0,n) */
function getJsonDiffChunkRanges(leftOut) {
  const n = leftOut.length
  if (n === 0) return []
  if (leftOut[0].type !== 'section') {
    return [[0, n]]
  }
  const ranges = []
  let s = 0
  while (s < n) {
    let e = s + 1
    while (e < n && leftOut[e].type !== 'section') e += 1
    ranges.push([s, e])
    s = e
  }
  return ranges
}

function jsonDiffLineText(leftOut, rightOut, j) {
  return leftOut[j].text || rightOut[j].text || ''
}

function jsonDiffLineIndent(line) {
  const m = String(line).match(/^(\s*)/)
  return m ? m[1].length : 0
}

function jsonDiffRowIsDiff(leftOut, rightOut, j) {
  const tL = leftOut[j].type
  if (tL === 'section' || tL === 'section-spacer') return false
  const tR = rightOut[j].type
  return tL !== 'same' || tR !== 'same'
}

/**
 * 某行存在差异时，保留其所在 JSON 对象块内的全部行（如 insert_orth 下三个字段一并展示）。
 */
function expandJsonDiffObjectContext(leftOut, rightOut, bodyStart, bodyEnd, diffIndices) {
  const keep = new Set(diffIndices)
  for (const j of diffIndices) {
    const lineJ = jsonDiffLineText(leftOut, rightOut, j)
    const indJ = jsonDiffLineIndent(lineJ)
    if (!lineJ.trim()) continue

    let openIdx = -1
    let openIndent = 0
    for (let u = j; u >= bodyStart; u -= 1) {
      const text = jsonDiffLineText(leftOut, rightOut, u)
      const ind = jsonDiffLineIndent(text)
      if (ind < indJ && /:\s*\{\s*$/.test(text.trim())) {
        openIdx = u
        openIndent = ind
        break
      }
    }
    if (openIdx < 0) {
      keep.add(j)
      continue
    }

    let closeIdx = openIdx
    for (let d = openIdx + 1; d < bodyEnd; d += 1) {
      const text = jsonDiffLineText(leftOut, rightOut, d)
      const ind = jsonDiffLineIndent(text)
      const trim = text.trim()
      if (ind <= openIndent && (trim === '}' || trim === '},')) {
        closeIdx = d
        break
      }
      closeIdx = d
    }
    for (let k = openIdx; k <= closeIdx; k += 1) keep.add(k)
  }
  return keep
}

/**
 * 后处理：去除过滤后「仅差异项」中悬空的尾逗号。
 * 当 }, 行后面的兄弟对象被过滤掉后，逗号需要移除以保持 JSON 合法。
 */
function fixTrailingCommas(rows) {
  for (let i = 0; i < rows.length; i += 1) {
    const text = rows[i].text
    const trimText = text.trim()
    if (trimText !== '},') continue
    const lineIndent = jsonDiffLineIndent(text)

    // 向后查找下一个非空行
    let nextText = ''
    let nextIndent = Infinity
    for (let k = i + 1; k < rows.length; k += 1) {
      const nt = rows[k].text.trim()
      if (nt) {
        nextText = nt
        nextIndent = jsonDiffLineIndent(rows[k].text)
        break
      }
    }

    // 如果下一个非空行是外层 } / ] / ],（缩进更小）或没有下一行，去掉逗号
    if (
      !nextText ||
      (nextIndent < lineIndent && (nextText === '}' || nextText === ']' || nextText === '],'))
    ) {
      rows[i] = { ...rows[i], text: text.replace(/,$/, '') }
    }
  }
}

/**
 * 仅保留有行级差异的行（del/add/blank/chg），去掉 same；带区域标题时仅保留「本段存在差异」的段。
 * 同一 JSON 对象内若有任意字段差异，则保留该对象块全部行。
 */
function filterJsonDiffRowsToDiffOnly(leftOut, rightOut) {
  if (leftOut.length !== rightOut.length) return { leftOut, rightOut }
  const n = leftOut.length
  if (n === 0) return { leftOut, rightOut }

  const outL = []
  const outR = []
  for (const [s, e] of getJsonDiffChunkRanges(leftOut)) {
    const hasSectionHeader = leftOut[s].type === 'section'
    const bodyStart = hasSectionHeader ? s + 1 : s
    const diffIndices = []
    for (let j = bodyStart; j < e; j += 1) {
      if (jsonDiffRowIsDiff(leftOut, rightOut, j)) diffIndices.push(j)
    }
    if (diffIndices.length === 0) continue

    const keepSet = expandJsonDiffObjectContext(leftOut, rightOut, bodyStart, e, diffIndices)

    // 始终保留外层大括号 { 和 }，确保过滤后 JSON 结构完整
    keepSet.add(bodyStart) // {
    keepSet.add(e - 1) // }

    if (hasSectionHeader) {
      outL.push(leftOut[s])
      outR.push(rightOut[s])
    }
    for (let j = bodyStart; j < e; j += 1) {
      if (keepSet.has(j)) {
        outL.push(leftOut[j])
        outR.push(rightOut[j])
      }
    }
  }

  // 后处理：修复过滤后悬空的尾逗号
  fixTrailingCommas(outL)
  fixTrailingCommas(outR)

  return { leftOut: outL, rightOut: outR }
}

/**
 * @param {object} [options]
 * @param {boolean} [options.onlyDiff] 仅显示有差异的行（对应「仅差异项」）
 */
function buildJsonDiffHtml(leftData, rightData, options = {}) {
  let { leftOut, rightOut } = buildJsonDiffRows(leftData, rightData)
  if (options.onlyDiff) {
    ;({ leftOut, rightOut } = filterJsonDiffRowsToDiffOnly(leftOut, rightOut))
  }
  const isEmpty = options.onlyDiff && leftOut.length === 0
  return {
    leftHtml: isEmpty ? '' : renderJsonDiffSide(leftOut),
    rightHtml: isEmpty ? '' : renderJsonDiffSide(rightOut),
    isEmpty,
  }
}

/** 与文本样式 pickJsonRegions 一致的区域分隔文案 */
function regionSectionBanner(regionKey) {
  return `=============${regionKey}=============`
}

/** 单个区域键下的 JSON 视图数据（与 buildJsonViewData 在非 all 时一致） */
function buildJsonViewDataSingle(map, key, jsonType) {
  if (!map || typeof map !== 'object') return {}
  if (jsonType === 1) return extractAbConfigAlgorithmUnits(map[key], key)
  if (jsonType === 2) return extractAeTigerConfigUnits(map[key], key)
  if (jsonType === 3) return extractCorridorUpdateUnits(map[key], key)
  if (jsonType === 4) return extractCorridorSetUnits(map[key], key)
  if (jsonType === 5) return extractReloadUnits(map[key], key)
  return extractRegionData(map, key)
}

/**
 * 「全部」+ JSON 样式：左右各自按本侧区域键分段做行级 diff，同索引段配对比对（键名可不同）
 * @param {object} [options]
 * @param {boolean} [options.onlyDiff]
 */
function buildJsonDiffHtmlAllRegions(leftMap, rightMap, jsonType, options = {}) {
  // 合并左右区域键并按字母排序，确保同一键名在两侧同位置出现
  const allKeys = [...new Set([
    ...Object.keys(leftMap || {}),
    ...Object.keys(rightMap || {}),
  ])].sort()
  const sectionCount = allKeys.length
  const leftAll = []
  const rightAll = []

  for (let idx = 0; idx < sectionCount; idx++) {
    const key = allKeys[idx]
    const leftHas = key in (leftMap || {})
    const rightHas = key in (rightMap || {})

    // 两侧均使用同一键名作 section 标题，确保分隔符文本一致
    leftAll.push({ type: 'section', text: regionSectionBanner(key), sign: ' ' })
    rightAll.push({ type: 'section', text: regionSectionBanner(key), sign: ' ' })

    const leftData = leftHas ? buildJsonViewDataSingle(leftMap, key, jsonType) : {}
    const rightData = rightHas ? buildJsonViewDataSingle(rightMap, key, jsonType) : {}
    // 当两侧 region 键相同且为特殊类型时，规范化键以支持跨 ab_config 匹配
    let normalizedLeft = leftData
    let normalizedRight = rightData
    if (jsonType >= 1 && jsonType <= 5 && leftHas && rightHas) {
      const norm = normalizeCrossConfigViewData(leftData, rightData, key, key)
      normalizedLeft = norm.leftNorm
      normalizedRight = norm.rightNorm
    }
    const { leftOut, rightOut } = buildJsonDiffRows(normalizedLeft, normalizedRight)
    leftAll.push(...leftOut)
    rightAll.push(...rightOut)

    if (idx < sectionCount - 1) {
      leftAll.push({ type: 'section-spacer', text: '', sign: ' ' })
      rightAll.push({ type: 'section-spacer', text: '', sign: ' ' })
    }
  }

  let leftOut = leftAll
  let rightOut = rightAll
  if (options.onlyDiff) {
    ;({ leftOut, rightOut } = filterJsonDiffRowsToDiffOnly(leftAll, rightAll))
  }
  const isEmpty = options.onlyDiff && leftOut.length === 0
  return {
    leftHtml: isEmpty ? '' : renderJsonDiffSide(leftOut),
    rightHtml: isEmpty ? '' : renderJsonDiffSide(rightOut),
    isEmpty,
  }
}

function resolveJsonType() {
  if (st.is_show_discrepancy === 'is_show_algorithm') return 1
  if (st.is_show_discrepancy === 'is_show_tiger') return 2
  if (st.is_show_discrepancy === 'is_show_corridor') return 3
  if (st.is_show_discrepancy === 'is_show_corridor_set') return 4
  if (st.is_show_discrepancy === 'is_show_reload') return 5
  return 0
}

function buildJsonViewData(map, regionKey, jsonType) {
  if (!map || typeof map !== 'object') return {}
  if (regionKey === 'all') {
    const out = {}
    for (const k of Object.keys(map)) {
      if (jsonType === 1) out[k] = extractAbConfigAlgorithmUnits(map[k], k)
      else if (jsonType === 2) out[k] = extractAeTigerConfigUnits(map[k], k)
      else if (jsonType === 3) out[k] = extractCorridorUpdateUnits(map[k], k)
      else if (jsonType === 4) out[k] = extractCorridorSetUnits(map[k], k)
      else if (jsonType === 5) out[k] = extractReloadUnits(map[k], k)
      else out[k] = extractRegionData(map, k)
    }
    return out
  }
  if (jsonType === 1) return extractAbConfigAlgorithmUnits(map[regionKey], regionKey)
  if (jsonType === 2) return extractAeTigerConfigUnits(map[regionKey], regionKey)
  if (jsonType === 3) return extractCorridorUpdateUnits(map[regionKey], regionKey)
  if (jsonType === 4) return extractCorridorSetUnits(map[regionKey], regionKey)
  if (jsonType === 5) return extractReloadUnits(map[regionKey], regionKey)
  return extractRegionData(map, regionKey)
}

/** 浏览器单张 canvas 尺寸上限（各浏览器约 16384px） */
const MAX_CANVAS_DIMENSION = 16384
const MAX_CANVAS_PIXELS = 64_000_000

function getElementContentSize(el) {
  const rect = el.getBoundingClientRect()
  return {
    width: Math.max(Math.ceil(rect.width), el.scrollWidth, el.offsetWidth, 1),
    height: Math.max(Math.ceil(rect.height), el.scrollHeight, el.offsetHeight, 1),
  }
}

function resolveCaptureScale(width, height, preferred = 2) {
  let scale = preferred
  const maxDim = Math.max(width, height, 1)
  if (maxDim * scale > MAX_CANVAS_DIMENSION) {
    scale = MAX_CANVAS_DIMENSION / maxDim
  }
  const pixels = width * height * scale * scale
  if (pixels > MAX_CANVAS_PIXELS) {
    scale = Math.sqrt(MAX_CANVAS_PIXELS / (width * height))
  }
  return Math.max(0.25, Math.min(preferred, scale))
}

/** html2canvas 对 flex + overflow 容器常算出 0 高度，克隆节点上展开后再截 */
function applyScreenshotCloneStyles(_doc, clonedRoot) {
  const nodes = [clonedRoot, ...clonedRoot.querySelectorAll('.result-row, .result-pane, .result-pane .el-card__body, .diff-html')]
  nodes.forEach((node) => {
    node.style.flex = 'none'
    node.style.minHeight = 'auto'
    node.style.maxHeight = 'none'
    node.style.height = 'auto'
    node.style.overflow = 'visible'
  })
}

async function captureElementScreenshot(el, preferredScale = 2) {
  const { width, height } = getElementContentSize(el)
  const scale = resolveCaptureScale(width, height, preferredScale)
  const canvas = await html2canvas(el, {
    useCORS: true,
    scale,
    backgroundColor: '#ffffff',
    logging: false,
    scrollX: 0,
    scrollY: -window.scrollY,
    onclone: (_doc, clonedEl) => {
      applyScreenshotCloneStyles(_doc, clonedEl)
    },
  })
  if (!canvas.width || !canvas.height) {
    throw new Error('画布尺寸为 0，请确认比对结果已加载完成')
  }
  return canvas
}

function downloadCanvasAsPng(canvas, filename) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (!blob || blob.size === 0) {
          reject(new Error('生成图片失败，截图内容可能过大，请缩小比对范围后重试'))
          return
        }
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.download = filename
        link.href = url
        link.click()
        URL.revokeObjectURL(url)
        resolve()
      },
      'image/png',
    )
  })
}

function mergeCanvasesVertically(canvases, { gap = 0, backgroundColor = '#ffffff' } = {}) {
  if (!canvases.length) {
    throw new Error('无可合并的截图')
  }
  const width = Math.max(...canvases.map((canvas) => canvas.width))
  const gapTotal = gap * (canvases.length - 1)
  const height = canvases.reduce((sum, canvas) => sum + canvas.height, 0) + gapTotal
  const merged = document.createElement('canvas')
  merged.width = width
  merged.height = height
  const ctx = merged.getContext('2d')
  ctx.fillStyle = backgroundColor
  ctx.fillRect(0, 0, width, height)
  let y = 0
  canvases.forEach((canvas, index) => {
    const x = Math.floor((width - canvas.width) / 2)
    ctx.drawImage(canvas, x, y)
    y += canvas.height
    if (index < canvases.length - 1) y += gap
  })
  return merged
}

function screenshotTimestamp() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}

async function onCaptureScreenshot() {
  const sourcesEl = compareSourcesRef.value
  const resultsEl = resultSectionRef.value
  if (!sourcesEl || !resultsEl) {
    ElMessage.warning('截图区域未就绪')
    return
  }
  loading.screenshot = true
  try {
    await nextTick()
    const ts = screenshotTimestamp()
    const [sourceCanvas, resultCanvas] = await Promise.all([
      captureElementScreenshot(sourcesEl, 2),
      captureElementScreenshot(resultsEl, 2),
    ])
    const mergedCanvas = mergeCanvasesVertically([sourceCanvas, resultCanvas], {
      gap: 20,
      backgroundColor: '#ffffff',
    })
    if (
      mergedCanvas.width > MAX_CANVAS_DIMENSION
      || mergedCanvas.height > MAX_CANVAS_DIMENSION
      || mergedCanvas.width * mergedCanvas.height > MAX_CANVAS_PIXELS
    ) {
      throw new Error('合并后图片过大，请缩小比对范围（如选择单个区域）后重试')
    }
    await downloadCanvasAsPng(mergedCanvas, `配置比对-${ts}.png`)
    ElMessage.success('截图已保存')
  } catch (e) {
    ElMessage.error('截图失败：' + (e.message || String(e)))
  } finally {
    loading.screenshot = false
  }
}

function runCompare() {
  if (isBatchMode.value) return
  const leftOk = Object.keys(st.api_left_region_map).length > 0
  const rightOk = Object.keys(st.api_right_region_map).length > 0
  if (!leftOk || !rightOk) {
    st.renderedLeftJson = ''
    st.renderedRightJson = ''
    return
  }

  loading.compare = true
  sendStatistic()

  try {
    /** 0：整段；1：algorithm；2：ae_tiger_config；3：corridor_update；4：corridor_set；5：reload */
    const jsonType = resolveJsonType()

    if (st.result_render_style === 'json_view') {
      const onlyDiff = st.is_show_discrepancy === 'is_show_diff'
      let leftHtml = ''
      let rightHtml = ''
      let emptyFiltered = false
      if (st.left_region === 'all' && st.right_region === 'all') {
        const r = buildJsonDiffHtmlAllRegions(
          st.api_left_region_map,
          st.api_right_region_map,
          jsonType,
          { onlyDiff }
        )
        leftHtml = r.leftHtml
        rightHtml = r.rightHtml
        emptyFiltered = r.isEmpty
      } else {
        if (jsonType >= 1 && jsonType <= 5) {
          // 特殊类型：按提取单元分段，每段添加节点头以标识来源节点
          let leftData = buildJsonViewData(st.api_left_region_map, st.left_region, jsonType)
          let rightData = buildJsonViewData(st.api_right_region_map, st.right_region, jsonType)
          const leftNorm = normalizeUnitsForMatching(leftData, st.left_region)
          const rightNorm = normalizeUnitsForMatching(rightData, st.right_region)
          const suffixes = [...new Set([...Object.keys(leftNorm), ...Object.keys(rightNorm)])].sort()

          if (suffixes.length === 0) {
            leftHtml = ''
            rightHtml = ''
            emptyFiltered = false
          } else {
            const leftAll = []
            const rightAll = []
            for (const suffix of suffixes) {
              const lInfo = leftNorm[suffix]
              const rInfo = rightNorm[suffix]
              const lDisplayId = lInfo ? lInfo.id : ((st.right_region || 'config') + '.' + suffix)
              const rDisplayId = rInfo ? rInfo.id : ((st.left_region || 'config') + '.' + suffix)
              const lObj = lInfo ? lInfo.value : {}
              const rObj = rInfo ? rInfo.value : {}

              // 节点头
              leftAll.push({ type: 'section', text: regionSectionBanner(lDisplayId), sign: ' ' })
              rightAll.push({ type: 'section', text: regionSectionBanner(rDisplayId), sign: ' ' })

              // 该单元的 JSON diff
              const { leftOut, rightOut } = buildJsonDiffRows(lObj, rObj)
              leftAll.push(...leftOut)
              rightAll.push(...rightOut)
            }

            let leftFinal = leftAll
            let rightFinal = rightAll
            if (onlyDiff) {
              ;({ leftOut: leftFinal, rightOut: rightFinal } = filterJsonDiffRowsToDiffOnly(leftAll, rightAll))
              emptyFiltered = leftFinal.length === 0
            }
            leftHtml = emptyFiltered ? '' : renderJsonDiffSide(leftFinal)
            rightHtml = emptyFiltered ? '' : renderJsonDiffSide(rightFinal)
          }
        } else {
          // 普通模式：直接使用原始数据比对（无需节点头，JSON key 本身就是标识）
          const leftData = buildJsonViewData(st.api_left_region_map, st.left_region, jsonType)
          const rightData = buildJsonViewData(st.api_right_region_map, st.right_region, jsonType)
          const r = buildJsonDiffHtml(leftData, rightData, { onlyDiff })
          leftHtml = r.leftHtml
          rightHtml = r.rightHtml
          emptyFiltered = r.isEmpty
        }
      }
      if (emptyFiltered) {
        st.renderedLeftJson = jsonDiffNoDiffHintHtml
        st.renderedRightJson = jsonDiffNoDiffHintHtml
      } else {
        st.renderedLeftJson = leftHtml
        st.renderedRightJson = rightHtml
      }
      return
    }

    if (st.left_region === 'all' && st.right_region === 'all') {
      const { left, right } = pickJsonRegions(
        st.api_left_region_map,
        st.api_right_region_map,
        jsonType
      )
      st.renderedLeftJson = left
      st.renderedRightJson = right
    } else if (st.left_region === 'all' || st.right_region === 'all') {
      st.renderedLeftJson = ''
      st.renderedRightJson = ''
    } else if (jsonType === 1) {
      const { left, right } = buildAlgorithmCompareHtml(
        st.api_left_region_map[st.left_region],
        st.api_right_region_map[st.right_region],
        {
          leftEntryKey: st.left_region,
          rightEntryKey: st.right_region,
        }
      )
      st.renderedLeftJson = left
      st.renderedRightJson = right
    } else if (jsonType === 2) {
      const { left, right } = buildTigerCompareHtml(
        st.api_left_region_map[st.left_region],
        st.api_right_region_map[st.right_region],
        {
          leftEntryKey: st.left_region,
          rightEntryKey: st.right_region,
        }
      )
      st.renderedLeftJson = left
      st.renderedRightJson = right
    } else if (jsonType === 3) {
      const { left, right } = buildCorridorUpdateCompareHtml(
        st.api_left_region_map[st.left_region],
        st.api_right_region_map[st.right_region],
        {
          leftEntryKey: st.left_region,
          rightEntryKey: st.right_region,
        }
      )
      st.renderedLeftJson = left
      st.renderedRightJson = right
    } else if (jsonType === 4) {
      const { left, right } = buildCorridorSetCompareHtml(
        st.api_left_region_map[st.left_region],
        st.api_right_region_map[st.right_region],
        {
          leftEntryKey: st.left_region,
          rightEntryKey: st.right_region,
        }
      )
      st.renderedLeftJson = left
      st.renderedRightJson = right
    } else if (jsonType === 5) {
      const { left, right } = buildReloadCompareHtml(
        st.api_left_region_map[st.left_region],
        st.api_right_region_map[st.right_region],
        {
          leftEntryKey: st.left_region,
          rightEntryKey: st.right_region,
        }
      )
      st.renderedLeftJson = left
      st.renderedRightJson = right
    } else {
      const leftA = extractRegionData(st.api_left_region_map, st.left_region)
      const rightB = extractRegionData(st.api_right_region_map, st.right_region)
      st.renderedLeftJson = compareJsonTree(leftA, rightB, 'left')
      st.renderedRightJson = compareJsonTree(leftA, rightB, 'right')
    }

    if (st.is_show_discrepancy === 'is_show_diff') {
      // 文本样式按 =============key============= 成对过滤并对齐；其它样式仍各自过滤
      if (st.result_render_style === 'text_view') {
        const paired = filterDiffDataPaired(st.renderedLeftJson, st.renderedRightJson)
        st.renderedLeftJson = paired.left
        st.renderedRightJson = paired.right
      } else {
        st.renderedLeftJson = filterDiffData(st.renderedLeftJson)
        st.renderedRightJson = filterDiffData(st.renderedRightJson)
      }
    } else if (st.is_show_discrepancy === 'is_show_banner') {
      st.renderedLeftJson = filterBannerData(st.renderedLeftJson)
      st.renderedRightJson = filterBannerData(st.renderedRightJson)
    }

    // 文本视图：按 key 补齐行数后转为结构化 <div>，保证同名分隔符左右对齐
    if (st.result_render_style === 'text_view') {
      if (st.is_show_discrepancy !== 'is_show_diff') {
        const aligned = alignTextHtmlByBanners(st.renderedLeftJson, st.renderedRightJson)
        st.renderedLeftJson = aligned.left
        st.renderedRightJson = aligned.right
      }
      st.renderedLeftJson = wrapTextAsStructuredHtml(st.renderedLeftJson)
      st.renderedRightJson = wrapTextAsStructuredHtml(st.renderedRightJson)
    }
  } finally {
    loading.compare = false
  }
}

// ---- AI 工具调用：自动填入参数 ----
onMounted(() => {
  const raw = sessionStorage.getItem('__ai_tool_call')
  if (!raw) return
  let payload
  try {
    payload = JSON.parse(raw)
  } catch {
    return
  }
  if (!payload || payload.tool !== 'config_compare' || !payload.params) return
  // 清除标记，避免重复触发
  sessionStorage.removeItem('__ai_tool_call')

  const { project, left_scheme, right_scheme } = payload.params
  if (!project || !left_scheme || !right_scheme) return

  // 验证项目名是否在已知列表中
  if (!COMPARE_PROJECTS.some((p) => p.name === project)) {
    ElMessage.warning(`AI 指定的项目「${project}」不在已知列表中，请手动选择`)
    return
  }

  // 自动填入参数并执行比对
  st.select_projects = [project]

  nextTick(async () => {
    await fetchGitInfo()
    const leftValue = encodeSchemeValue(project, left_scheme)
    const rightValue = encodeSchemeValue(project, right_scheme)
    st.select_left_Adwaynum = leftValue
    st.select_right_Adwaynum = rightValue
    await nextTick()
    if (st.select_left_Adwaynum === leftValue) {
      await getLeftadwaynumJson()
    }
    if (st.select_right_Adwaynum === rightValue) {
      await getRightadwaynumJson()
    }
    ElMessage.success(`已自动加载「${projectDisplayName(project)}」的比对：${left_scheme} vs ${right_scheme}`)
  })
})

/** 处理 AI 对话框内发出的实时工具调用（无需页面跳转） */
async function onAiToolCallLive(params) {
  if (!params || !params.project || !params.left_scheme || !params.right_scheme) return

  if (!COMPARE_PROJECTS.some((p) => p.name === params.project)) {
    ElMessage.warning(`AI 指定的项目「${params.project}」不在已知列表中，请手动选择`)
    return
  }

  st.select_projects = [params.project]
  await nextTick()
  await fetchGitInfo()
  const leftValue = encodeSchemeValue(params.project, params.left_scheme)
  const rightValue = encodeSchemeValue(params.project, params.right_scheme)
  st.select_left_Adwaynum = leftValue
  st.select_right_Adwaynum = rightValue
  await nextTick()
  if (st.select_left_Adwaynum === leftValue) {
    await getLeftadwaynumJson()
  }
  if (st.select_right_Adwaynum === rightValue) {
    await getRightadwaynumJson()
  }
  ElMessage.success(`AI 已自动加载比对：${params.left_scheme} vs ${params.right_scheme}`)
}

onMounted(() => {
  window.addEventListener('ai-tool-call-live', onAiToolCallLive)
})

onUnmounted(() => {
  window.removeEventListener('ai-tool-call-live', onAiToolCallLive)
})

</script>

<style scoped>
.config-compare {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: calc(100vh - 96px);
  padding: 0 4px 20px;
  box-sizing: border-box;
}

.card-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}
.title-text {
  font-size: 17px;
  font-weight: 600;
  color: #303133;
}

.filter-card {
  border-radius: 10px;
  flex-shrink: 0;
}
.filter-card :deep(.el-card__body) {
  padding-top: 8px;
}
.filter-form {
  width: 100%;
}

.global-filter-row {
  align-items: flex-start;
}

.display-options-wrap {
  margin-top: 8px;
}

.display-options-panel {
  padding: 16px 18px 18px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  box-sizing: border-box;
}

.display-options-panel :deep(.el-form-item) {
  margin-bottom: 18px;
}
.display-options-panel :deep(.el-form-item:last-child) {
  margin-bottom: 0;
}

.compare-sources-wrap {
  margin-top: 4px;
}

.screenshot-form-item :deep(.el-form-item__label) {
  color: transparent;
  user-select: none;
}
.screenshot-action-row {
  display: flex;
  align-items: center;
  min-height: var(--el-component-size);
}
.screenshot-btn {
  flex-shrink: 0;
}
.screenshot-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.display-mode-item :deep(.el-form-item__content) {
  line-height: 1.4;
}
.display-mode-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  width: 100%;
}
.display-mode-group :deep(.el-radio-button) {
  margin: 0;
}
.display-mode-group :deep(.el-radio-button__inner) {
  padding: 8px 12px;
}

.section-divider {
  margin: 16px 0 20px;
}
.compare-sources-wrap > .section-divider:first-child {
  margin-top: 8px;
}
.section-divider-text {
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  letter-spacing: 0.04em;
}

.project-form-item :deep(.el-form-item__content) {
  flex-direction: column;
  align-items: stretch;
}

.project-select-row {
  display: flex;
  align-items: stretch;
  gap: 10px;
  width: 100%;
  max-width: 100%;
}

.project-select {
  flex: 1;
  min-width: 0;
}

.project-platform-tag {
  flex-shrink: 0;
  align-self: center;
  padding: 0 12px;
  height: 32px;
  line-height: 32px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: #fff;
}
.project-platform-tag.gp {
  background: linear-gradient(135deg, #409eff 0%, #66b1ff 100%);
}
.project-platform-tag.ios {
  background: linear-gradient(135deg, #606266 0%, #909399 100%);
}
.project-platform-tag.multi {
  background: linear-gradient(135deg, #e6a23c 0%, #f3d19e 100%);
  color: #5c3d00;
}
.project-platform-tag.none {
  background: var(--el-fill-color);
  color: var(--el-text-color-secondary);
  border: 1px dashed var(--el-border-color);
}

.sync-cache-btn {
  flex-shrink: 0;
  align-self: center;
}

.project-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}

.w-full {
  width: 100%;
}

/* 方案下拉：选中框内长文案换行（覆盖 Element Plus 单行省略） */
.scheme-select :deep(.el-select__wrapper) {
  align-items: flex-start;
  min-height: var(--el-component-size);
}
.scheme-select :deep(.el-select__selection) {
  flex-wrap: wrap;
  align-items: flex-start;
}
.scheme-select :deep(.el-select__selected-item.el-select__placeholder) {
  position: relative;
  top: auto;
  left: auto;
  transform: none;
  z-index: 0;
  width: 100%;
  max-width: 100%;
  overflow: visible;
  text-overflow: clip;
  white-space: normal;
}
.scheme-select :deep(.scheme-select-trigger-label) {
  display: block;
  width: 100%;
  max-width: 100%;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.45;
}
.scheme-select :deep(.el-select__suffix) {
  align-self: flex-start;
  margin-top: 4px;
}

.slot-radios {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.region-radios {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  padding: 0;
  margin: 0;
}

.region-group-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px 8px;
}

.region-group-tag {
  font-size: 11px;
  font-weight: 700;
  color: #606266;
  flex-shrink: 0;
  text-align: left;
  line-height: var(--el-radio-line-height, 22px);
  padding-top: 2px;
  margin-bottom: 2px;
}

.region-subs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}

.region-subs-no-tag {
  /* 无标签时不需要额外处理 */
}

.region-sub-row {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 2px 8px;
}

.region-sub-tag {
  font-size: 10px;
  font-weight: 400;
  color: #c0c4cc;
  flex-shrink: 0;
  line-height: var(--el-radio-line-height, 22px);
}

/* 长 key 名在 radio 内自动换行 */
.region-sub-row :deep(.el-radio__label) {
  word-break: break-word;
  overflow-wrap: anywhere;
  white-space: normal;
  line-height: 1.5;
}

.scheme-status-alert {
  margin-bottom: 12px;
}

.compare-sources {
  margin-top: 0;
}

.batch-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 4px;
  margin-bottom: 4px;
}

.source-panel {
  height: 100%;
  padding: 16px 18px 18px;
  background: var(--el-fill-color-lighter);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 10px;
  box-sizing: border-box;
}

.source-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.source-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  color: #fff;
}
.source-badge.left {
  background: linear-gradient(135deg, #409eff, #66b1ff);
}
.source-badge.right {
  background: linear-gradient(135deg, #67c23a, #95d475);
}
.source-title {
  font-weight: 600;
  color: #303133;
}

.result-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 12px;
}

.result-section-head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 16px;
  flex-shrink: 0;
}
.result-section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}
.result-section-sub {
  font-size: 12px;
  color: #a8abb2;
}

.result-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  flex: 1;
  min-height: min(58vh, 780px);
}
@media (max-width: 992px) {
  .result-row {
    grid-template-columns: 1fr;
    min-height: auto;
  }
  .result-pane {
    min-height: 320px;
  }
}

.result-pane {
  min-width: 0;
  min-height: 280px;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
}
.result-pane :deep(.el-card__body) {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.pane-title {
  font-weight: 600;
  font-size: 14px;
  color: #606266;
}

.diff-html {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px 18px;
  background: #f6f8fa;
  border-radius: 8px;
  /* 等宽拉丁 + 中文回退，长文可读性优于纯 Courier */
  font-family:
    'JetBrains Mono',
    ui-monospace,
    'SF Mono',
    'Cascadia Code',
    'Cascadia Mono',
    Menlo,
    Monaco,
    Consolas,
    'PingFang SC',
    'Hiragino Sans GB',
    'Microsoft YaHei',
    'Noto Sans SC',
    monospace;
  font-size: 14px;
  font-weight: 400;
  font-variant-numeric: tabular-nums;
  line-height: 1.72;
  letter-spacing: 0.01em;
  color: #1f2328;
  border: 1px solid var(--el-border-color-lighter);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  /* 区域内放不下时自动换行（长 JSON、无空格字符串） */
  overflow-wrap: anywhere;
  word-break: break-word;
  white-space: normal;
}

.diff-json-pre {
  margin: 0;
  padding: 8px 0;
}

.diff-html :deep(.diff-json-line) {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  align-items: start;
  min-height: 24px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  border-radius: 4px;
}

.diff-html :deep(.diff-json-sign) {
  user-select: none;
  opacity: 0.9;
  font-weight: 600;
  text-align: center;
}

.diff-html :deep(.diff-json-text) {
  min-width: 0;
}

.diff-html :deep(.diff-json-line-same) {
  background: transparent;
}

.diff-html :deep(.diff-json-line-add) {
  background: #eaf7ee;
  color: #1a7f37;
}

.diff-html :deep(.diff-json-line-del) {
  background: #ffeef0;
  color: #cf222e;
}

/* 同 key 值不同：仅背景色区分，不显示 - / + */
.diff-html :deep(.diff-json-line-chg) {
  background: #fff8e6;
  color: #9a6700;
}

.diff-html :deep(.diff-json-line-chg .diff-json-sign) {
  visibility: hidden;
}

.diff-html :deep(.diff-json-line-blank) {
  background: transparent;
  color: #8c959f;
}

.diff-html :deep(.diff-json-line-section) {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 32px;
  margin-top: 10px;
  margin-bottom: 6px;
  padding: 6px 10px;
  font-weight: 600;
  font-size: 13px;
  letter-spacing: 0.02em;
  color: #0550ae;
  background: linear-gradient(90deg, #ddf4ff 0%, #f6f8fa 55%, #f6f8fa 100%);
  border: 1px solid #b6e0fe;
  border-radius: 6px;
}

.diff-html :deep(.diff-json-line-section:first-child) {
  margin-top: 0;
}

.diff-html :deep(.diff-json-line-section .diff-json-sign) {
  display: none;
}

.diff-html :deep(.diff-json-line-section .diff-json-text) {
  flex: 1;
  text-align: center;
  font-family: ui-monospace, monospace;
}

.diff-html :deep(.diff-json-line-section-spacer) {
  min-height: 10px;
  background: transparent;
}

.diff-html :deep(.diff-json-line-section-spacer .diff-json-sign) {
  opacity: 0;
}

.diff-html :deep(.diff-json-line-empty) {
  display: block;
  color: #656d76;
  font-family: var(--el-font-family);
  padding: 6px 2px;
}

.diff-html :deep(.empty-hint) {
  margin: 0;
  color: #656d76;
  font-family: var(--el-font-family);
  font-size: 14px;
  font-weight: 400;
  letter-spacing: normal;
  line-height: 1.65;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.diff-html :deep(.diff-chg),
.diff-html :deep(.diff-new),
.diff-html :deep(.diff-add),
.diff-html :deep(.diff-same) {
  overflow-wrap: anywhere;
  word-break: break-word;
  font-weight: 500;
}
.diff-html :deep(.diff-chg) {
  color: #cf222e;
  font-weight: 600;
}
.diff-html :deep(.diff-chg-prefix) {
  margin-right: 2px;
}
.diff-html :deep(.diff-new) {
  color: #1a7f37;
  font-weight: 600;
}
.diff-html :deep(.diff-add) {
  color: #9a6700;
  font-weight: 500;
}
.diff-html :deep(.diff-same) {
  color: #57606a;
  font-weight: 400;
}
.diff-html :deep(.diff-missing) {
  display: inline-block;
  max-width: 100%;
  padding: 10px 12px;
  margin: 4px 0;
  font-family: var(--el-font-family);
  font-size: 13px;
  font-weight: 400;
  line-height: 1.55;
  color: #9a6700;
  background: #fff8e6;
  border: 1px dashed #e6a23c;
  border-radius: 6px;
}
.diff-html :deep(.diff-sep) {
  border: none;
  border-top: 1px dashed #dcdfe6;
  margin: 8px 0;
}
.diff-html :deep(hr) {
  border: none;
  border-top: 1px dashed #dcdfe6;
  margin: 8px 0;
}

/* ---- 悬浮 AI 助手按钮 ---- */
.ai-float-btn {
  position: fixed;
  bottom: 40px;
  right: 40px;
  z-index: 1000;
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #409eff, #66b1ff);
  box-shadow: 0 4px 16px rgba(64, 158, 255, 0.4);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.25s, box-shadow 0.25s;
  user-select: none;
}

.ai-float-btn:hover {
  transform: scale(1.12);
  box-shadow: 0 6px 24px rgba(64, 158, 255, 0.55);
}

.ai-float-btn:active {
  transform: scale(0.95);
}

.ai-robot-icon {
  width: 36px;
  height: 36px;
  pointer-events: none;
}

/* 呼吸灯脉冲动画 */
.ai-float-btn::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  border: 2px solid rgba(64, 158, 255, 0.35);
  animation: ai-pulse 2s ease-in-out infinite;
}

@keyframes ai-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.6;
  }
  50% {
    transform: scale(1.08);
    opacity: 0;
  }
}
</style>

<!-- 下拉层 teleport 到 body，须用非 scoped 样式 -->
<style>
.scheme-select-dropdown .el-select-dropdown__item {
  height: auto;
  min-height: var(--el-option-height, 34px);
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.45;
  padding-top: 8px;
  padding-bottom: 8px;
  overflow: visible;
  text-overflow: clip;
}
.scheme-select-dropdown .el-select-dropdown__item .scheme-option-label {
  display: block;
  white-space: normal;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.45;
  padding-right: 8px;
}
</style>
