<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { RadarChart } from 'echarts/charts'
import { RadarComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

// 按需注册，避免整包引入 echarts（诊断页只用雷达图）
echarts.use([RadarChart, RadarComponent, TooltipComponent, CanvasRenderer])

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '260px' },
})

const el = ref(null)
let chart = null
let observer = null

function render() {
  if (!chart) return
  chart.setOption(props.option, true)
}

onMounted(() => {
  chart = echarts.init(el.value, null, { renderer: 'canvas' })
  render()
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(el.value)
})

watch(() => props.option, render, { deep: true })

onBeforeUnmount(() => {
  observer?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div ref="el" class="chart" :style="{ height }" />
</template>

<style scoped>
.chart {
  width: 100%;
}
</style>
