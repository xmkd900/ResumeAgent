<script setup>
import { computed, ref } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'

import SectionCard from '@/components/SectionCard.vue'
import { formatFileSize } from '@/utils/format'

const props = defineProps({
  resume: { type: Object, default: null },
  uploading: { type: Boolean, default: false },
  uploadProgress: { type: Number, default: 0 },
  analyzing: { type: Boolean, default: false },
  reparsing: { type: Boolean, default: false },
  canDiagnose: { type: Boolean, default: false },
  pollExpired: { type: Boolean, default: false },
})

const emit = defineEmits(['upload', 'diagnose', 'refresh', 'reparse'])

const fileInput = ref(null)
const dragging = ref(false)

const STATUS_MAP = {
  pending: { dot: 'dot--pending', text: '解析中', hint: '正在抽取文本并结构化分节，通常 5-15 秒' },
  done: { dot: 'dot--live', text: '解析完成', hint: '已完成文本抽取与结构分节，可以开始诊断' },
  failed: { dot: 'dot--failed', text: '解析失败', hint: '文件可能已损坏、加密或为扫描件' },
}

const status = computed(() => {
  if (props.uploading) return { dot: 'dot--pending', text: '上传中', hint: '正在上传文件' }
  if (!props.resume) return null
  return STATUS_MAP[props.resume.parse_status] || null
})

const failureHint = computed(() => {
  if (props.resume?.parse_status !== 'failed') return ''
  return props.resume.parse_error || STATUS_MAP.failed.hint
})

const busy = computed(() => props.uploading || props.analyzing)

function pickFile() {
  if (busy.value) return
  fileInput.value?.click()
}

function handleFiles(files) {
  if (busy.value) return
  const file = files?.[0]
  if (file) emit('upload', file)
}

function onFileChange(event) {
  handleFiles(event.target.files)
  event.target.value = ''
}

function onDrop(event) {
  dragging.value = false
  handleFiles(event.dataTransfer?.files)
}
</script>

<template>
  <SectionCard class="upload-card" title="上传简历" subtitle="PDF / DOCX，异步解析后进入诊断">
    <template #extra>
      <span class="pill pill--outline">
        <span class="dot" :class="status?.dot || ''" />
        {{ status?.text || '待上传' }}
      </span>
    </template>

    <div
      class="dropzone"
      :class="{ 'is-dragging': dragging, 'is-filled': !!resume, 'is-busy': busy }"
      role="button"
      tabindex="0"
      @click="pickFile"
      @keydown.enter.prevent="pickFile"
      @keydown.space.prevent="pickFile"
      @dragover.prevent
      @dragenter.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input
        ref="fileInput"
        type="file"
        accept=".pdf,.docx"
        class="dropzone__input"
        @change="onFileChange"
      />

      <div v-if="uploading" class="uploading">
        <span class="spinner" aria-hidden="true" />
        <p class="uploading__text">正在上传… {{ uploadProgress }}%</p>
        <div class="progress"><i :style="{ width: `${uploadProgress}%` }" /></div>
      </div>

      <template v-else-if="!resume">
        <span class="dropzone__icon">
          <el-icon><UploadFilled /></el-icon>
        </span>
        <p class="dropzone__title">拖拽简历到这里，或点击选择文件</p>
        <p class="dropzone__hint">PDF / DOCX · 单份不超过 10 MB · 扫描件暂不支持</p>
      </template>

      <template v-else>
        <div class="file">
          <span class="file__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none">
              <path d="M6 3h8l4 4v14H6z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
              <path d="M14 3v4h4M9 13h6M9 16.5h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
            </svg>
          </span>
          <div class="file__meta">
            <p class="file__name truncate">{{ resume.filename }}</p>
            <p class="file__sub">
              <span>{{ formatFileSize(resume.file_size) }}</span>
              <span class="file__sep">·</span>
              <span class="file__status" :class="`file__status--${resume.parse_status}`">
                <span class="dot" :class="status?.dot" />
                {{ status?.text }}
              </span>
            </p>
          </div>
          <span class="file__replace">重新上传</span>
        </div>
        <p class="dropzone__hint dropzone__hint--inline">{{ status?.hint }}</p>
        <p v-if="failureHint" class="dropzone__error">{{ failureHint }}</p>
      </template>
    </div>

    <div v-if="resume?.parse_status === 'pending' && pollExpired" class="poll-hint">
      <span>状态更新超时，解析可能仍在后台进行。</span>
      <div class="poll-hint__actions">
        <button type="button" @click="emit('refresh')">刷新状态</button>
        <button type="button" :disabled="reparsing" @click="emit('reparse')">
          {{ reparsing ? '提交中…' : '重新解析' }}
        </button>
      </div>
    </div>

    <div class="upload-foot">
      <p class="upload-foot__note">解析在后台异步执行，不阻塞页面；解析失败可重新上传。</p>
      <el-button
        type="primary"
        :loading="analyzing"
        :disabled="!canDiagnose"
        @click="emit('diagnose')"
      >
        {{ analyzing ? '正在诊断…' : '开始诊断' }}
      </el-button>
    </div>
  </SectionCard>
</template>

<style scoped>
.dropzone {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 176px;
  padding: 24px;
  border-radius: var(--radius);
  border: 1.5px dashed var(--line-strong);
  background: var(--surface-2);
  cursor: pointer;
  text-align: center;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.dropzone:hover,
.dropzone:focus-visible {
  border-color: #b9b7ea;
  background: #fbfaff;
  outline: none;
}

.dropzone.is-dragging {
  border-color: var(--primary);
  background: var(--primary-soft);
}

.dropzone.is-filled {
  align-items: stretch;
  justify-content: center;
  gap: 10px;
  border-style: solid;
  border-color: var(--line);
  background: var(--surface);
  cursor: default;
  padding: 20px;
}

.dropzone.is-busy {
  cursor: progress;
}

.dropzone__input {
  display: none;
}

.dropzone__icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: var(--primary-soft);
  color: var(--primary);
  font-size: 20px;
  margin-bottom: 8px;
}

.dropzone__title {
  font-size: 13.5px;
  font-weight: 600;
  color: var(--ink-2);
}

.dropzone__hint {
  font-size: 11.5px;
  color: var(--ink-3);
}

.dropzone__hint--inline {
  text-align: left;
  padding-left: 2px;
}

.dropzone__error {
  font-size: 11.5px;
  line-height: 1.6;
  color: #b03e3d;
  background: var(--danger-soft);
  border-radius: 8px;
  padding: 7px 10px;
  text-align: left;
}

.file {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--line);
  background: var(--surface-2);
}

.file__icon {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: #fff;
  border: 1px solid var(--line);
  color: var(--primary);
  flex: none;
}

.file__meta {
  min-width: 0;
  flex: 1;
}

.file__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}

.file__sub {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  font-size: 11px;
  color: var(--ink-3);
}

.file__sep {
  color: var(--ink-4);
}

.file__status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.file__status--done {
  color: #0b7269;
}

.file__status--pending {
  color: #96600f;
}

.file__status--failed {
  color: #b03e3d;
}

.file__replace {
  flex: none;
  font-size: 12px;
  font-weight: 550;
  color: var(--primary);
  padding: 4px 6px;
  border-radius: 6px;
}

.file__replace:hover {
  background: var(--primary-soft);
}

.uploading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.uploading__text {
  font-size: 12.5px;
  color: var(--ink-2);
}

.spinner {
  width: 26px;
  height: 26px;
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

.progress {
  width: 70%;
  height: 4px;
  border-radius: 4px;
  background: var(--surface-3);
  overflow: hidden;
}

.progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #8b89f2, var(--primary));
  transition: width 0.2s ease;
}

.poll-hint {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  background: var(--warn-soft);
  font-size: 11.5px;
  color: #7d5814;
}

.poll-hint button {
  border: 0;
  background: transparent;
  color: #96600f;
  font-weight: 600;
  font-size: 11.5px;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.poll-hint button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.poll-hint__actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.upload-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-top: 16px;
}

.upload-foot__note {
  font-size: 11.5px;
  color: var(--ink-3);
  line-height: 1.6;
}

@media (max-width: 640px) {
  .upload-foot {
    flex-direction: column;
    align-items: stretch;
  }

  .upload-foot :deep(.el-button) {
    width: 100%;
  }
}
</style>
