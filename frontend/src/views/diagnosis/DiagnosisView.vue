<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import EmptyState from '@/components/EmptyState.vue'
import PageHeader from '@/components/PageHeader.vue'
import SectionCard from '@/components/SectionCard.vue'
import { useResumeDiagnosis } from '@/composables/useResumeDiagnosis'

import DimensionRadar from './components/DimensionRadar.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import IssueList from './components/IssueList.vue'
import JdCard from './components/JdCard.vue'
import ReportSummary from './components/ReportSummary.vue'
import UploadCard from './components/UploadCard.vue'

const {
  resumes,
  total,
  listLoading,
  listError,
  activeResume,
  reportsLoading,
  activeReport,
  pageError,
  uploading,
  uploadProgress,
  analyzing,
  reparsing,
  pollExpired,
  isParsing,
  parseFailed,
  canDiagnose,
  init,
  reload,
  selectResume,
  uploadFile,
  reparseActiveResume,
  runDiagnosis,
  refreshActiveResume,
} = useResumeDiagnosis()

const jd = ref('')
const reportEl = ref(null)
const historyEl = ref(null)

const issues = computed(() =>
  Array.isArray(activeReport.value?.issues) ? activeReport.value.issues : [],
)
const highCount = computed(() => issues.value.filter((item) => item.severity === 'high').length)

onMounted(init)

async function handleUpload(file) {
  const resume = await uploadFile(file)
  if (resume) ElMessage.success('上传成功，正在后台解析')
}

async function handleDiagnose() {
  const report = await runDiagnosis(jd.value)
  if (!report) return
  ElMessage.success('诊断完成')
  await nextTick()
  reportEl.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToHistory() {
  historyEl.value?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function scrollToUpload() {
  document.querySelector('.upload-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function handleReparse() {
  const resume = await reparseActiveResume()
  if (resume) ElMessage.success('已提交重新解析，请稍候')
}

async function refreshList() {
  await reload()
  if (activeResume.value) await refreshActiveResume()
}
</script>

<template>
  <div class="page">
    <PageHeader
      eyebrow="Resume Review"
      title="简历诊断"
      subtitle="上传简历，可选粘贴目标 JD。报告包含综合分、维度雷达与三段式改写建议——每条都引用原文。"
    >
      <template #actions>
        <el-button :icon="Refresh" :loading="listLoading" @click="refreshList">刷新</el-button>
        <el-button plain @click="scrollToHistory">历史诊断</el-button>
      </template>
    </PageHeader>

    <el-alert
      v-if="listError"
      class="page-alert"
      type="error"
      :title="listError"
      :closable="false"
      show-icon
    />
    <el-alert
      v-else-if="pageError"
      class="page-alert"
      type="error"
      :title="pageError"
      :closable="false"
      show-icon
    />

    <div class="grid">
      <UploadCard
        class="span-7"
        :resume="activeResume"
        :uploading="uploading"
        :upload-progress="uploadProgress"
        :analyzing="analyzing"
        :reparsing="reparsing"
        :can-diagnose="canDiagnose"
        :poll-expired="pollExpired"
        @upload="handleUpload"
        @diagnose="handleDiagnose"
        @refresh="refreshActiveResume"
        @reparse="handleReparse"
      />
      <JdCard v-model="jd" class="span-5" />
    </div>

    <div ref="reportEl" class="report">
      <template v-if="activeReport">
        <div class="grid">
          <SectionCard class="span-8">
            <ReportSummary :report="activeReport" :resume="activeResume" />
          </SectionCard>

          <SectionCard
            class="span-4"
            title="维度雷达"
            subtitle="0-100 分，由内置 rubric 各维度加权得出"
          >
            <DimensionRadar :dimensions="activeReport.dimension_scores" />
          </SectionCard>
        </div>

        <div class="grid grid--second">
          <SectionCard
            class="span-8"
            title="问题清单"
            :subtitle="`${issues.length} 条建议 · 引用原文 → 问题说明 → 改写示例`"
          >
            <template #extra>
              <span class="pill pill--soft">{{ highCount }} 高优先级</span>
            </template>
            <IssueList :issues="issues" />
          </SectionCard>

          <div ref="historyEl" class="span-4">
            <HistoryPanel
              :resumes="resumes"
              :active-id="activeResume?.id"
              :loading="listLoading"
              :total="total"
              @select="selectResume"
            />
          </div>
        </div>
      </template>

      <div v-else class="grid">
        <SectionCard class="span-8">
          <EmptyState
            v-if="!activeResume"
            title="上传简历，生成第一份诊断报告"
            description="支持 PDF / DOCX。上传后会自动解析，完成后点击「开始诊断」。"
          />

          <div v-else-if="isParsing" class="state">
            <span class="spinner" aria-hidden="true" />
            <p class="state__title">正在解析简历</p>
            <p class="state__desc">
              正在抽取文本并做结构化分节，通常需要 5-15 秒；解析完成后会自动刷新状态。
            </p>
          </div>

          <EmptyState
            v-else-if="parseFailed"
            title="简历解析失败"
            :description="activeResume.parse_error || '文件可能已损坏、加密或为扫描件，请换一份文件重试。'"
          >
            <div class="state-actions">
              <el-button type="primary" :loading="reparsing" @click="handleReparse">
                重新解析
              </el-button>
              <el-button @click="scrollToUpload">重新上传</el-button>
            </div>
          </EmptyState>

          <div v-else-if="reportsLoading" class="state" aria-label="加载报告">
            <div class="skeleton-line skeleton-line--lg" />
            <div class="skeleton-line" />
            <div class="skeleton-line" />
            <div class="skeleton-line skeleton-line--sm" />
          </div>

          <EmptyState
            v-else
            title="这份简历还没有诊断报告"
            description="点击「开始诊断」生成报告；补充目标 JD 可以获得岗位匹配维度。"
          >
            <el-button type="primary" :loading="analyzing" :disabled="!canDiagnose" @click="handleDiagnose">
              {{ analyzing ? '正在诊断…' : '开始诊断' }}
            </el-button>
          </EmptyState>
        </SectionCard>

        <div ref="historyEl" class="span-4">
          <HistoryPanel
            :resumes="resumes"
            :active-id="activeResume?.id"
            :loading="listLoading"
            :total="total"
            @select="selectResume"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
}

.page-alert {
  margin-bottom: 16px;
  border-radius: 10px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 18px;
}

.grid--second {
  margin-top: 18px;
}

.span-7 {
  grid-column: span 7;
}

.span-5 {
  grid-column: span 5;
}

.span-8 {
  grid-column: span 8;
}

.span-4 {
  grid-column: span 4;
}

.report {
  margin-top: 18px;
  scroll-margin-top: 78px;
}

.state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 44px 24px;
  color: var(--ink-3);
}

.state-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.state__title {
  margin-top: 14px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-2);
}

.state__desc {
  margin-top: 6px;
  max-width: 360px;
  font-size: 12px;
  line-height: 1.7;
}

.spinner {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2.5px solid var(--line);
  border-top-color: var(--primary);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.skeleton-line {
  height: 10px;
  border-radius: 5px;
  background: var(--surface-3);
  margin-bottom: 10px;
  width: 100%;
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-line--lg {
  height: 16px;
  width: 42%;
  margin-bottom: 18px;
}

.skeleton-line--sm {
  width: 60%;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.55;
  }
}

@media (max-width: 1080px) {
  .span-7,
  .span-5,
  .span-8,
  .span-4 {
    grid-column: span 12;
  }
}
</style>
