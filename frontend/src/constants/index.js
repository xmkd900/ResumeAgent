/**
 * 全局常量：枚举 → 中文 label 的映射放在前端（协议保持英文枚举，见 ARCHITECTURE.md v1.2 自查第 6 条）
 */

/** issues[].type 英文枚举 → 中文标签 */
export const ISSUE_TYPE_LABELS = {
  quantification: '成果量化',
  structure: '结构表达',
  relevance: '岗位匹配',
  depth: '项目深度',
  completeness: '信息完整',
  wording: '表述规范',
}

/** issues[].severity → 视觉与文案 */
export const SEVERITY_META = {
  high: { label: '高优先级', tone: 'danger', hint: '影响筛简历的第一眼判断' },
  medium: { label: '中优先级', tone: 'warn', hint: '会削弱说服力' },
  low: { label: '低优先级', tone: 'muted', hint: '锦上添花' },
}

/** judgement.verdict 三档 → 人话标签（不展示内部分数） */
export const VERDICT_META = {
  good: { label: '回答扎实', tone: 'success' },
  partial: { label: '基本到位', tone: 'warn' },
  bad: { label: '需要补强', tone: 'danger' },
}

/** weak_point.source 枚举 → 中文 */
export const WEAK_SOURCE_LABELS = {
  interview: '模拟面试',
  self_test: '练习自测',
}

export const WEAK_SEVERITY_WEIGHT = { high: 3, medium: 2, low: 1 }

/** 检索模式 */
export const SEARCH_MODES = [
  { value: 'hybrid', label: '混合检索', hint: 'BM25 + 向量 → RRF → Rerank' },
  { value: 'vector', label: '纯向量', hint: '仅 Qdrant 语义召回' },
  { value: 'bm25', label: '纯 BM25', hint: '仅关键词稀疏召回' },
]

/** 检索调试台参数（与后端配置项同名，仅展示） */
export const RETRIEVAL_PARAMS = [
  { key: 'RECALL_TOP_K', value: '50' },
  { key: 'RRF_K', value: '60' },
  { key: 'FINAL_TOP_K', value: '10' },
]

/** 工具页可见性：开发环境恒开，生产需显式开启 */
export const DEBUG_ENABLED =
  import.meta.env.DEV || String(import.meta.env.VITE_ENABLE_DEBUG) === 'true'

export const APP_NAME = 'IntelliCareer'
