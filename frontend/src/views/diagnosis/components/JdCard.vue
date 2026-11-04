<script setup>
import SectionCard from '@/components/SectionCard.vue'

const text = defineModel({ type: String, default: '' })

const SAMPLE_JD = `岗位：后端开发工程师（2026 校招）
职责：负责交易/订单核心链路设计与开发；参与系统性能优化与稳定性建设。
要求：熟悉 Java 与 Spring Boot；掌握 MySQL 索引与慢查询优化；了解 Redis 缓存设计；有高并发项目经验者优先。`
</script>

<template>
  <SectionCard
    class="jd-card"
    title="JD 对照（可选）"
    subtitle="粘贴目标岗位 JD，诊断会额外给出岗位匹配维度"
  >
    <el-input
      v-model="text"
      type="textarea"
      :rows="7"
      maxlength="2000"
      show-word-limit
      resize="none"
      placeholder="把目标岗位的 JD 粘贴到这里：职责、硬性要求、加分项…"
    />
    <div class="jd-foot">
      <span class="muted">未填写 JD 时，只按通用 rubric 评分</span>
      <el-button link type="primary" @click="text = SAMPLE_JD">填入示例</el-button>
    </div>
  </SectionCard>
</template>

<style scoped>
.jd-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  font-size: 11.5px;
}
</style>
