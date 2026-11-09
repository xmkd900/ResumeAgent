import { onScopeDispose, ref } from 'vue'

/**
 * 浏览器语音转写（Web Speech API）。
 *
 * 不依赖后端：Chrome/Edge 走内置识别服务，中文用 zh-CN。
 * 兼容性差异较大，因此导出 supported，让界面决定是否显示入口。
 */
const SpeechRecognition =
  typeof window !== 'undefined'
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null

const ERROR_MESSAGES = {
  'not-allowed': '麦克风权限被拒绝，请在浏览器地址栏的权限设置里允许',
  'service-not-allowed': '当前浏览器禁止使用语音识别服务',
  'audio-capture': '没有检测到可用的麦克风',
  network: '语音识别服务网络异常，请稍后再试',
  'language-not-supported': '当前浏览器不支持中文语音识别',
}

export function useSpeechInput({ onFinal } = {}) {
  const supported = Boolean(SpeechRecognition)
  const listening = ref(false)
  const interim = ref('')
  const error = ref('')

  let recognition = null

  function build() {
    if (!supported) return null
    if (recognition) return recognition

    recognition = new SpeechRecognition()
    recognition.lang = 'zh-CN'
    recognition.continuous = true
    recognition.interimResults = true

    recognition.onstart = () => {
      listening.value = true
      error.value = ''
    }

    recognition.onend = () => {
      listening.value = false
      interim.value = ''
    }

    recognition.onerror = (event) => {
      listening.value = false
      interim.value = ''
      // 用户没说话/主动中止不算错误
      if (event.error === 'no-speech' || event.error === 'aborted') return
      error.value = ERROR_MESSAGES[event.error] || `语音识别失败：${event.error}`
    }

    recognition.onresult = (event) => {
      let finalText = ''
      let interimText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index]
        const text = result[0]?.transcript || ''
        if (result.isFinal) finalText += text
        else interimText += text
      }
      interim.value = interimText
      if (finalText.trim()) onFinal?.(finalText.trim())
    }

    return recognition
  }

  function start() {
    const instance = build()
    if (!instance) {
      error.value = '当前浏览器不支持语音输入，建议使用 Chrome 或 Edge'
      return false
    }
    try {
      error.value = ''
      instance.start()
      return true
    } catch (err) {
      // 连续点击时浏览器会抛 InvalidStateError，忽略即可
      if (err?.name !== 'InvalidStateError') {
        error.value = '无法启动语音识别，请检查麦克风权限'
      }
      return false
    }
  }

  function stop() {
    if (!recognition) return
    try {
      recognition.stop()
    } catch {
      // 已经停止时忽略
    }
    listening.value = false
    interim.value = ''
  }

  function toggle() {
    return listening.value ? (stop(), false) : start()
  }

  onScopeDispose(stop)

  return { supported, listening, interim, error, start, stop, toggle }
}
