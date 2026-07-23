<script setup>
import { ref, computed } from 'vue'

// ── .env 開關 ──────────────────────────────────────────────
// VITE_USE_REAL_BACKEND=true  → 預設打真實後端；false → 用模擬資料
// VITE_API_BASE_URL           → FastAPI 位址（預設 http://localhost:8000）
const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
const useReal = ref(import.meta.env.VITE_USE_REAL_BACKEND === 'true')

// ── Agent 定義：對齊後端 stage_graph.py 的 STAGE_LABELS 與執行順序 ──
// budget → weather → [travel ∥ booking 平行] → traffic → scheduler
const agents = ref([
  { id: 'budget',    label: '預算管家', en: 'Budget',   icon: '💰', status: 'pending' },
  { id: 'weather',   label: '天氣專員', en: 'Weather',  icon: '☁️', status: 'pending' },
  { id: 'travel',    label: '景點專員', en: 'Travel',   icon: '🗺️', status: 'pending' },
  { id: 'booking',   label: '訂房專員', en: 'Booking',  icon: '🏨', status: 'pending' },
  { id: 'traffic',   label: '交通專員', en: 'Traffic',  icon: '🚆', status: 'pending' },
  { id: 'scheduler', label: '排程專員', en: 'Schedule', icon: '📅', status: 'pending' },
])

// 流程步驟：每一格是一個 superstep；含兩個 id 的步驟代表平行 fan-out
const steps = [
  { agents: ['budget'] },
  { agents: ['weather'] },
  { agents: ['travel', 'booking'], parallel: true },
  { agents: ['traffic'] },
  { agents: ['scheduler'] },
]

const query = ref('幫我規劃台北三天兩夜、兩人同行、總預算兩萬元的旅行，喜歡美食和文青景點。')
const isRunning = ref(false)
const waitingBackend = ref(false) // 動畫跑完但真實後端仍在回應中
const result = ref('')
const notice = ref('') // fallback / 錯誤提示橫幅

const getAgent = (id) => agents.value.find((a) => a.id === id)
const completedCount = computed(() => agents.value.filter((a) => a.status === 'completed').length)
const isDone = computed(() => !isRunning.value && result.value !== '')

// 依步驟目前狀態決定上方連接線顏色（該步驟全部完成 → 轉綠）
const stepDone = (step) => step.agents.every((id) => getAgent(id).status === 'completed')

// 節點卡片的 Tailwind class（四種狀態）
const nodeClass = (status) => ({
  pending:   'border-slate-700 bg-slate-800/40 text-slate-400',
  running:   'border-amber-400 bg-amber-400/10 text-amber-50 shadow-lg shadow-amber-500/20 ring-2 ring-amber-400/40 scale-[1.02]',
  completed: 'border-emerald-400 bg-emerald-400/10 text-emerald-50',
  error:     'border-rose-400 bg-rose-400/10 text-rose-50',
}[status])

const badgeClass = (status) => ({
  pending:   'bg-slate-700 text-slate-300',
  running:   'bg-amber-400/20 text-amber-200',
  completed: 'bg-emerald-400/20 text-emerald-200',
  error:     'bg-rose-400/20 text-rose-200',
}[status])

const statusText = { pending: '待命', running: '執行中', completed: '完成', error: '失敗' }

const MOCK_RESULT = `# 台北 3 天 2 夜 · 美食文青之旅

**需求摘要**：2 人｜總預算 20,000 元｜預算階層：適中

## Day 1
- 10:00 松山文創園區 — 文青市集與展覽
- 12:30 富錦街午餐 — 巷弄咖啡與早午餐
- 15:00 誠品信義店 — 選書與生活選物
- 19:00 饒河街夜市 — 胡椒餅、藥燉排骨

## Day 2
- 09:00 大稻埕 — 迪化街老屋巡禮
- 12:00 永樂市場 — 在地小吃
- 14:30 北投溫泉 — 泡湯放鬆
- 18:30 陽明山夜景晚餐

## Day 3
- 10:00 故宮博物院
- 13:00 士林在地餐廳
- 15:30 伴手禮採買 → 賦歸

---
🏨 **住宿**：西門町商旅 2 晚，約 6,400 元
🚆 **交通**：高鐵 + 台北捷運一日券，約 3,200 元
💰 **預算**：預估總花費 18,600 元 / 20,000 元（剩餘 1,400 元）`

const wait = (ms) => new Promise((r) => setTimeout(r, ms))
const setStatus = (ids, status) => ids.forEach((id) => (getAgent(id).status = status))

// 依序點亮節點的動畫；mock 與 real 兩種模式共用（real 模式當作「樂觀 UI」）
const TIMELINE = [
  { ids: ['budget'], ms: 1000 },
  { ids: ['weather'], ms: 1000 },
  { ids: ['travel', 'booking'], ms: 3000 }, // 平行：兩個節點同時 running
  { ids: ['traffic'], ms: 2000 },
  { ids: ['scheduler'], ms: 1000 },
]

async function animateTimeline() {
  for (const { ids, ms } of TIMELINE) {
    setStatus(ids, 'running')
    await wait(ms)
    setStatus(ids, 'completed')
  }
}

function reset() {
  agents.value.forEach((a) => (a.status = 'pending'))
  result.value = ''
  notice.value = ''
  waitingBackend.value = false
}

// ── 模式一：純前端模擬（離線可用） ──────────────────────────
async function simulateAgentExecution() {
  reset()
  isRunning.value = true
  await animateTimeline()
  result.value = MOCK_RESULT
  isRunning.value = false
}

// ── 模式二：串接真實後端（FastAPI GET /chat/{query}） ───────
async function fetchBackend() {
  // 真實 LLM + E2B 可能跑數十秒，設 120s 逾時保護
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 120000)
  try {
    const url = `${API_BASE}/chat/${encodeURIComponent(query.value)}`
    const res = await fetch(url, { signal: ctrl.signal })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } finally {
    clearTimeout(timer)
  }
}

// 用後端回傳的 stages[].status 校正每個節點的最終狀態（success → 綠，其它 → 紅）
function applyRealStages(stages) {
  if (!Array.isArray(stages)) return
  const byId = Object.fromEntries(stages.map((s) => [s.stage, s]))
  agents.value.forEach((a) => {
    const s = byId[a.id]
    if (!s) return // 後端沒跑到這個 stage 就維持動畫後的狀態
    a.status = s.status === 'success' ? 'completed' : 'error'
  })
}

async function runRealBackend() {
  reset()
  isRunning.value = true

  // 立刻發出真實請求（先包成不會 reject 的結果物件，避免 unhandled rejection）
  const pending = fetchBackend()
    .then((data) => ({ ok: true, data }))
    .catch((error) => ({ ok: false, error }))

  // 同時跑「樂觀」的依序點亮動畫，讓畫面在等待期間是活的、並講出平行的故事
  await animateTimeline()

  waitingBackend.value = true
  const outcome = await pending
  waitingBackend.value = false

  if (outcome.ok) {
    applyRealStages(outcome.data.stages)
    result.value = outcome.data.response || '（後端未回傳文字結果）'
  } else {
    // 連不上後端 → 自動 fallback 回模擬資料，demo 不中斷
    notice.value = `⚠️ 無法連線真實後端（${outcome.error.message}），已自動改用模擬結果。`
    result.value = MOCK_RESULT
  }
  isRunning.value = false
}

// 送出按鈕的分派器
function run() {
  if (isRunning.value) return
  useReal.value ? runRealBackend() : simulateAgentExecution()
}

// ── 一鍵複製結果到剪貼簿 ──────────────────────────────────
const copied = ref(false)
async function copyResult() {
  if (!result.value) return
  try {
    await navigator.clipboard.writeText(result.value)
  } catch {
    // navigator.clipboard 在非 https / 舊瀏覽器可能不可用，退回 execCommand
    const ta = document.createElement('textarea')
    ta.value = result.value
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    try {
      document.execCommand('copy')
    } finally {
      document.body.removeChild(ta)
    }
  }
  copied.value = true
  setTimeout(() => (copied.value = false), 1500)
}
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-slate-100 antialiased">
    <div class="mx-auto max-w-7xl px-6 py-8">
      <!-- Header -->
      <header class="mb-8 flex items-center gap-3">
        <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-fuchsia-500 text-xl font-bold shadow-lg shadow-indigo-500/30">V</div>
        <div>
          <h1 class="text-2xl font-bold tracking-tight">VoyaGen</h1>
          <p class="text-sm text-slate-400">Multi-Agent 旅遊規劃系統 · 即時執行監控</p>
        </div>
      </header>

      <div class="grid gap-6 lg:grid-cols-2">
        <!-- ══════════ 左半部：輸入區 ══════════ -->
        <section class="flex flex-col rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur">
          <label class="mb-2 text-sm font-semibold text-slate-300">你的旅遊需求</label>
          <textarea
            v-model="query"
            :disabled="isRunning"
            rows="7"
            class="w-full resize-none rounded-xl border border-slate-700 bg-slate-950/70 p-4 text-sm leading-relaxed text-slate-100 placeholder-slate-500 outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-400/30 disabled:opacity-60"
            placeholder="例如：幫我規劃台北三天兩夜、兩人同行、預算兩萬..."
          />

          <!-- 資料來源切換：模擬 / 真實後端 -->
          <div class="mt-4 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/50 p-3">
            <div class="min-w-0">
              <p class="text-sm font-medium text-slate-200">資料來源</p>
              <p class="truncate text-[11px] text-slate-500">
                {{ useReal ? `真實後端 · ${API_BASE}` : '模擬資料（離線可用）' }}
              </p>
            </div>
            <button
              @click="useReal = !useReal"
              :disabled="isRunning"
              role="switch"
              :aria-checked="useReal"
              class="relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border-0 p-0 transition-colors disabled:opacity-50"
              :class="useReal ? 'bg-emerald-500' : 'bg-slate-600'"
            >
              <span
                class="inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-200"
                :class="useReal ? 'translate-x-[22px]' : 'translate-x-0.5'"
              />
            </button>
          </div>

          <button
            @click="run"
            :disabled="isRunning"
            class="mt-4 flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 transition hover:brightness-110 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <svg v-if="isRunning" class="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
            </svg>
            <span>{{ isRunning ? 'Agent 執行中…' : (useReal ? '🚀 開始規劃行程（真實後端）' : '🚀 開始規劃行程（模擬）') }}</span>
          </button>

          <!-- fallback / 錯誤提示 -->
          <div v-if="notice" class="mt-4 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs leading-relaxed text-rose-200">
            {{ notice }}
          </div>

          <!-- 進度摘要 -->
          <div class="mt-6 rounded-xl border border-slate-800 bg-slate-950/50 p-4">
            <div class="mb-2 flex items-center justify-between text-xs text-slate-400">
              <span>整體進度</span>
              <span>{{ completedCount }} / {{ agents.length }} 完成</span>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-slate-800">
              <div
                class="h-full rounded-full bg-gradient-to-r from-emerald-400 to-teal-400 transition-all duration-500"
                :style="{ width: `${(completedCount / agents.length) * 100}%` }"
              />
            </div>
          </div>
        </section>

        <!-- ══════════ 右半部：流程圖 + 結果 ══════════ -->
        <section class="flex flex-col gap-6">
          <!-- Workflow Visualizer -->
          <div class="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur">
            <h2 class="mb-5 text-sm font-semibold uppercase tracking-wider text-slate-400">Agent 執行流程</h2>

            <div class="flex flex-col items-stretch">
              <template v-for="(step, i) in steps" :key="i">
                <!-- 連接線（第一步之前不畫） -->
                <div
                  v-if="i > 0"
                  class="mx-auto my-1 h-5 w-px transition-colors duration-500"
                  :class="stepDone(steps[i - 1]) ? 'bg-emerald-400' : 'bg-slate-700'"
                />

                <!-- 平行步驟：並排容器 + 標籤 -->
                <div v-if="step.parallel" class="relative rounded-2xl border border-dashed border-indigo-400/50 bg-indigo-500/5 p-3">
                  <span class="absolute -top-2.5 left-4 rounded-full bg-slate-900 px-2 text-[11px] font-semibold text-indigo-300">
                    ⚡ 平行處理 · Parallel
                  </span>
                  <div class="grid grid-cols-2 gap-3">
                    <div
                      v-for="id in step.agents"
                      :key="id"
                      class="flex items-center gap-3 rounded-xl border p-3 transition-all duration-300"
                      :class="nodeClass(getAgent(id).status)"
                    >
                      <span class="text-xl">{{ getAgent(id).icon }}</span>
                      <div class="min-w-0 flex-1">
                        <p class="truncate text-sm font-semibold">{{ getAgent(id).label }}</p>
                        <p class="truncate text-[11px] opacity-60">{{ getAgent(id).en }}</p>
                      </div>
                      <!-- 狀態指示 -->
                      <svg v-if="getAgent(id).status === 'running'" class="h-5 w-5 shrink-0 animate-spin text-amber-300" viewBox="0 0 24 24" fill="none">
                        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                        <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                      </svg>
                      <span v-else-if="getAgent(id).status === 'completed'" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-400 text-xs font-bold text-slate-900">✓</span>
                      <span v-else-if="getAgent(id).status === 'error'" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-400 text-xs font-bold text-slate-900">✕</span>
                      <span v-else class="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-600" />
                    </div>
                  </div>
                </div>

                <!-- 一般步驟：單一節點 -->
                <div
                  v-else
                  class="flex items-center gap-3 rounded-xl border p-4 transition-all duration-300"
                  :class="nodeClass(getAgent(step.agents[0]).status)"
                >
                  <span class="text-2xl">{{ getAgent(step.agents[0]).icon }}</span>
                  <div class="flex-1">
                    <p class="text-sm font-semibold">{{ getAgent(step.agents[0]).label }}</p>
                    <p class="text-[11px] opacity-60">{{ getAgent(step.agents[0]).en }}</p>
                  </div>
                  <span class="rounded-full px-2.5 py-1 text-[11px] font-medium" :class="badgeClass(getAgent(step.agents[0]).status)">
                    {{ statusText[getAgent(step.agents[0]).status] }}
                  </span>
                  <svg v-if="getAgent(step.agents[0]).status === 'running'" class="h-5 w-5 shrink-0 animate-spin text-amber-300" viewBox="0 0 24 24" fill="none">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                    <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                  </svg>
                  <span v-else-if="getAgent(step.agents[0]).status === 'completed'" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-400 text-xs font-bold text-slate-900">✓</span>
                  <span v-else-if="getAgent(step.agents[0]).status === 'error'" class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-rose-400 text-xs font-bold text-slate-900">✕</span>
                </div>
              </template>
            </div>
          </div>

          <!-- 最終結果區 -->
          <div class="flex-1 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur">
            <div class="mb-4 flex items-center gap-2">
              <h2 class="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-slate-400">
                最終行程
                <span v-if="isDone" class="rounded-full bg-emerald-400/20 px-2 py-0.5 text-[11px] normal-case text-emerald-300">已生成</span>
              </h2>
              <button
                v-if="result"
                @click="copyResult"
                class="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/60 px-3 py-1.5 text-xs font-medium text-slate-200 transition hover:bg-slate-700 active:scale-95"
                :class="copied ? 'border-emerald-500/50 text-emerald-300' : ''"
              >
                <svg v-if="copied" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                </svg>
                <svg v-else class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <rect x="9" y="9" width="11" height="11" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                </svg>
                <span>{{ copied ? '已複製' : '複製結果' }}</span>
              </button>
            </div>

            <!-- 空狀態 / 等待後端 -->
            <div v-if="!result" class="flex h-40 flex-col items-center justify-center text-center text-slate-500">
              <template v-if="waitingBackend">
                <svg class="h-7 w-7 animate-spin text-indigo-300" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                  <path class="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
                </svg>
                <p class="mt-2 text-sm">⏳ 等待真實後端回應…（真實 LLM / E2B 執行中，可能需數十秒）</p>
              </template>
              <template v-else>
                <span class="text-3xl">🧭</span>
                <p class="mt-2 text-sm">{{ isRunning ? 'Agent 正在生成行程，請稍候…' : '送出需求後，這裡會顯示完整行程規劃' }}</p>
              </template>
            </div>

            <!--
              目前以純文字（whitespace-pre-wrap）顯示 Markdown 原文。
              未來要渲染成 HTML：
                npm install marked dompurify
                import { marked } from 'marked'
                import DOMPurify from 'dompurify'
              再把下面的 <div> 換成：
                <div class="prose prose-invert max-w-none" v-html="DOMPurify.sanitize(marked.parse(result))" />
              （建議搭配 @tailwindcss/typography 的 prose class 自動美化標題/清單排版）
            -->
            <div v-else class="whitespace-pre-wrap rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-sm leading-relaxed text-slate-200">{{ result }}</div>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>
