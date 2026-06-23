<template>
  <div class="app-layout">
    <!-- Main Countdown Card -->
    <div class="timer-container main-card">
      <h1 class="main-title">⏱️ Timer</h1>
      
      <!-- Input Mode -->
      <div v-if="!isRunning" class="input-form">
        <div class="input-row">
          <div class="input-group">
            <label>HH</label>
            <input v-model.number="inputHours" type="number" min="0" max="999" placeholder="00" />
          </div>
          <span class="separator">:</span>
          
          <div class="input-group">
            <label>MM</label>
            <input 
              :value="displayMinutes" 
              @keydown="handleKeyDown('minutes', $event)"
              type="text" 
              inputmode="numeric"
              placeholder="00" 
            />
          </div>
          <span class="separator">:</span>
          
          <div class="input-group">
            <label>SS</label>
            <input 
              :value="displaySeconds" 
              @keydown="handleKeyDown('seconds', $event)"
              type="text" 
              inputmode="numeric"
              placeholder="00" 
            />
          </div>
        </div>
        
        <button @click="startTimer" class="btn-start">Start Timer</button>
      </div>

      <!-- Live Countdown Screen -->
      <div v-else class="ticker-screen">
        <div class="countdown-display" :class="{ 'time-up': timeLeft === 0 }">
          {{ formattedTime }}
        </div>
        <button @click="resetTimer" class="btn-reset">Reset</button>
      </div>

      <div v-if="loading" class="status-msg">
        <span class="spinner"></span> Connecting to backend...
      </div>
    </div>

    <!-- Presets Management Card -->
    <div class="timer-container side-card stored-section">
      <h3>💾 Stored Presets</h3>
      
      <div class="save-row">
        <input 
          v-model="timerLabel" 
          type="text" 
          placeholder="Timer Name (e.g. Pomodoro)" 
          class="label-input" 
          @keyup.enter="storeTimerConfig"
        />
        <button @click="storeTimerConfig" class="btn-save">Save Setup</button>
      </div>
      
      <p v-if="savedTimers.length === 0" class="empty-msg">No stored presets found.</p>
      <ul class="timers-list" v-else>
        <li v-for="timer in savedTimers" :key="timer.id" @click="loadPreset(timer)">
          <span class="preset-name">★ {{ timer.label }}</span>
          <span class="preset-duration">{{ formatSecondsToHMS(timer.duration_seconds) }}</span>
          <button @click.stop="confirmDelete(timer)" class="btn-delete-row" title="Delete Preset">🗑️</button>
        </li>
      </ul>
    </div>

    <!-- CUSTOM DIALOGS & NOTIFICATIONS (Replaces browser Alert/Confirm blocks) -->
    <Transition name="fade">
      <div v-if="notification" class="custom-notification" :class="notification.type">
        {{ notification.message }}
      </div>
    </Transition>

    <Transition name="fade">
      <div v-if="confirmModal.show" class="modal-overlay">
        <div class="modal-card">
          <h4>Confirm Action</h4>
          <p>{{ confirmModal.message }}</p>
          <div class="modal-actions">
            <button @click="closeConfirm(false)" class="btn-cancel">Cancel</button>
            <button @click="closeConfirm(true)" class="btn-danger-confirm">Delete</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted, onMounted, reactive } from 'vue'

// Basic Reactive Variables
const inputHours = ref(0)
const minutesVal = ref(0)
const secondsVal = ref(0)
const timerLabel = ref('')
const savedTimers = ref([])

const timeLeft = ref(0)
const isRunning = ref(false)
const loading = ref(false)
let timerInterval = null

// Custom Notification & Confirmation Modal State
const notification = ref(null)
const confirmModal = reactive({
  show: false,
  message: '',
  onConfirm: null,
})

// Display Helpers
const displayMinutes = computed(() => String(minutesVal.value).padStart(2, '0'))
const displaySeconds = computed(() => String(secondsVal.value).padStart(2, '0'))
const formattedTime = computed(() => formatSecondsToHMS(timeLeft.value))

onMounted(() => {
  fetchSavedTimers()
})

// Utility: Trigger a custom elegant overlay notification banner
function showNotification(message, type = 'error') {
  notification.value = { message, type }
  setTimeout(() => {
    notification.value = null
  }, 3500)
}

// Utility: Trigger custom confirmation dialog
function confirmDelete(timer) {
  confirmModal.message = `Are you sure you want to delete "${timer.label}"?`
  confirmModal.onConfirm = () => deleteTimer(timer.id)
  confirmModal.show = true
}

function closeConfirm(isConfirmed) {
  if (isConfirmed && confirmModal.onConfirm) {
    confirmModal.onConfirm()
  }
  confirmModal.show = false
  confirmModal.onConfirm = null
}

// --- BACKEND INTEGRATION ---

async function fetchSavedTimers() {
  try {
    const response = await fetch('http://localhost:8000/api/timers')
    if (response.ok) {
      savedTimers.value = await response.json()
    }
  } catch (error) {
    console.error("Failed to fetch stored configs:", error)
  }
}

async function storeTimerConfig() {
  const totalSeconds = (inputHours.value * 3600) + (minutesVal.value * 60) + secondsVal.value
  
  if (!timerLabel.value.trim()) {
    showNotification("Please name your timer before storing it.")
    return
  }
  if (totalSeconds <= 0) {
    showNotification("Cannot save an empty timer duration.")
    return
  }

  try {
    const response = await fetch('http://localhost:8000/api/timers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        label: timerLabel.value,
        duration_seconds: totalSeconds
      })
    })
    
    if (response.ok) {
      timerLabel.value = ''
      showNotification("Preset saved successfully!", "success")
      await fetchSavedTimers()
    } else {
      const err = await response.json()
      showNotification(err.detail || "Error saving preset.")
    }
  } catch (error) {
    console.error("Failed to fetch stored configs:", error)
    showNotification("Error saving configurations to server.")
  }
}

async function deleteTimer(id) {
  try {
    const res = await fetch(`http://localhost:8000/api/timers/${id}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' }
    })

    if (res.ok) {
      showNotification("Preset deleted.", "success")
      await fetchSavedTimers()
    } else {
      const err = await res.json()
      showNotification(err.detail || "Failed to delete timer")
    }
  } catch (error) {
    console.error("Failed to fetch stored configs:", error)
    showNotification("Error communicating with backend to delete timer.")
  }
}

// --- UTILITY LOGIC ---

function loadPreset(timer) {
  const hours = Math.floor(timer.duration_seconds / 3600)
  const minutes = Math.floor((timer.duration_seconds % 3600) / 60)
  const seconds = timer.duration_seconds % 60

  inputHours.value = hours
  minutesVal.value = minutes
  secondsVal.value = seconds
  showNotification(`Loaded: ${timer.label}`, "success")
}

function formatSecondsToHMS(totalSecs) {
  const hours = Math.floor(totalSecs / 3600)
  const minutes = Math.floor((totalSecs % 3600) / 60)
  const seconds = totalSecs % 60
  return [
    String(hours).padStart(2, '0'),
    String(minutes).padStart(2, '0'),
    String(seconds).padStart(2, '0')
  ].join(':')
}

// Keep single digit appending logic stable
function handleKeyDown(type, event) {
  const key = event.key
  const targetRef = type === 'minutes' ? minutesVal : secondsVal

  if (['Backspace', 'Delete', 'Tab', 'ArrowLeft', 'ArrowRight'].includes(key)) {
    if (key === 'Backspace') {
      event.preventDefault()
      targetRef.value = Math.floor(targetRef.value / 10)
    }
    return
  }

  if (!/^[0-9]$/.test(key)) {
    event.preventDefault()
    return
  }

  event.preventDefault()
  
  // 3. Take the current 2-digit display string (e.g., "08")
  const currentStr = String(targetRef.value).padStart(2, '0')
  
  // 4. Windows Behavior: Slide the new digit in from the right 
  // "08" + "6" becomes "86", then we slice the LAST two digits.
  // BUT to ensure typing '6' right after '08' gives '06', we check if the 
  // first digit was just placeholder padding.
  let combinedStr = currentStr + key
  
  // Keep only the last 2 digits
  const finalStr = combinedStr.slice(-2)
  
  let display_value = parseInt(finalStr, 10)

  if (display_value > 59) {
    display_value = parseInt(key, 10)
  }

  // Convert back to a number for your backend logic
  targetRef.value = display_value
}

async function startTimer() {
  // Combine Hours (unchanged) + Sliding Minutes + Sliding Seconds
  const totalSeconds = (inputHours.value * 3600) + (minutesVal.value * 60) + secondsVal.value
  
  if (totalSeconds <= 0) {
    showNotification("Please enter a valid time duration.")
    return
  }
  
  loading.value = true
  try {
    const response = await fetch('http://localhost:8000/api/timer/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration_seconds: totalSeconds })
    })
    
    const data = await response.json()
    
    if (response.ok) {
      timeLeft.value = data.duration
      isRunning.value = true
      startTickerLoop()
    } else {
      showNotification(data.detail || "Failed to start timer")
    }
  } catch (error) {
    console.error("Failed to connect to backend:", error)
    showNotification("Backend server is offline!")
  } finally {
    loading.value = false
  }
}

function startTickerLoop() {
  clearInterval(timerInterval)
  timerInterval = setInterval(() => {
    if (timeLeft.value > 0) {
      timeLeft.value--
    } else {
      clearInterval(timerInterval)
    }
  }, 1000)
}

function resetTimer() {
  clearInterval(timerInterval)
  timeLeft.value = 0
  isRunning.value = false
}

onUnmounted(() => {
  clearInterval(timerInterval)
})
</script>

<style scoped>
.app-layout {
  display: flex;
  gap: 30px;
  width: 100%;
  margin: 40px auto;
  padding: 0 20px;
  align-items: stretch;
  box-sizing: border-box;
  position: relative;
}

@media (min-width: 1025px) {
  .app-layout {
    max-width: 1024px;
  }
}

@media (max-width: 1024px) {
  .app-layout {
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  .app-layout {
    flex-direction: column;
    margin: 20px auto;
  }
}

.timer-container {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: #1a1a1a;
  color: #f3f4f6;
  padding: 35px;
  border-radius: 16px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  border: 1px solid #2e2e2e;
  display: flex;
  flex-direction: column;
}

.main-card {
  flex: 1.2;
}

.side-card {
  flex: 1;
}

.main-title {
  font-size: 1.35rem;
  color: #a1a1aa;
  margin-top: 0;
  margin-bottom: 30px;
  letter-spacing: 0.5px;
  text-align: center;
}

.input-row {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 30px;
  background: #121212;
  padding: 15px;
  border-radius: 12px;
  border: 1px solid #262626;
}

.input-group {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.input-group label {
  font-size: 0.75rem;
  font-weight: 700;
  color: #71717a;
  margin-bottom: 6px;
  letter-spacing: 1px;
}

.input-group input {
  background: transparent;
  border: none;
  color: #fff;
  width: 75px;
  font-size: 2rem;
  text-align: center;
  font-family: 'Courier New', monospace;
  font-weight: bold;
}

.input-group input::-webkit-outer-spin-button,
.input-group input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.input-group input[type=number] {
  -moz-appearance: textfield;
}

input[type="text"] {
  caret-color: #42b883;
}

.input-group input:focus {
  outline: none;
  color: #42b883;
}

.separator {
  font-size: 2rem;
  font-weight: bold;
  color: #3f3f46;
  margin: -4px 10px 0 10px;
  font-family: 'Courier New', monospace;
}

.save-row {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.label-input {
  flex: 1;
  background: #121212;
  border: 1px solid #262626;
  color: #fff;
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 0.95rem;
  transition: border-color 0.2s;
}

.label-input:focus {
  outline: none;
  border-color: #3498db;
}

button {
  padding: 12px 24px;
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s ease;
}

.btn-start {
  background-color: #42b883;
  color: #0c2d1c;
  width: 100%;
  font-size: 1.05rem;
  box-shadow: 0 4px 12px rgba(66, 184, 131, 0.2);
}
.btn-start:hover {
  background-color: #4cd195;
  transform: translateY(-1px);
}

.btn-save {
  background-color: #262626;
  color: #3498db;
  border: 1px solid #2e2e2e;
}
.btn-save:hover {
  background-color: #2980b9;
  color: white;
}

.countdown-display {
  font-size: 4.5rem;
  font-weight: 800;
  color: #42b883;
  margin: 20px 0 35px 0;
  letter-spacing: -1px;
  text-align: center;
  font-family: 'Courier New', monospace;
  text-shadow: 0 0 20px rgba(66, 184, 131, 0.15);
}

.countdown-display.time-up {
  color: #ef4444;
  text-shadow: 0 0 20px rgba(239, 68, 68, 0.3);
  animation: blink 1s infinite;
}

.btn-reset {
  background-color: #262626;
  color: #ef4444;
  border: 1px solid #3b1818;
  width: 100%;
}
.btn-reset:hover {
  background-color: #ef4444;
  color: white;
}

.stored-section h3 {
  font-size: 1.1rem;
  color: #e4e4e7;
  margin-top: 0;
  margin-bottom: 20px;
}

.empty-msg {
  color: #52525b;
  font-size: 0.95rem;
  text-align: center;
  margin: auto 0;
}

.timers-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 360px;
  overflow-y: scroll;
  padding-right: 4px; /* Space to keep layout clean when scrollbar appears */
  max-height: 280px; /* Base height for tablets / small screens */

}

/* Screen-size based adjustments for list height */
@media (min-height: 800px) and (min-width: 769px) {
  .timers-list {
    max-height: 420px; /* Taller viewport desktop height */
  }
}

@media (max-height: 650px) {
  .timers-list {
    max-height: 160px; /* Landscape/Short screens */
  }
}

/* Premium Dark-Themed Custom Scrollbar styling for Webkit */
.timers-list::-webkit-scrollbar {
  width: 6px;
}
.timers-list::-webkit-scrollbar-track {
  background: #121212;
  border-radius: 8px;
}
.timers-list::-webkit-scrollbar-thumb {
  background: #2e2e2e;
  border-radius: 8px;
  transition: background 0.2s ease;
}
.timers-list::-webkit-scrollbar-thumb:hover {
  background: #42b883;
}


.timers-list li {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #121212;
  padding: 14px 18px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s ease;
  white-space: nowrap;
  gap: 15px;
}

.timers-list li:hover {
  background: #1e1e1e;
  border-color: #42b883;
  transform: translateX(4px);
}

.preset-name {
  color: #e4e4e7;
  font-weight: 500;
}
.preset-duration {
  color: #a1a1aa;
  font-family: 'Courier New', monospace;
  font-weight: bold;
}

.btn-delete-row {
  background: transparent;
  border: none;
  font-size: 1rem;
  padding: 0.5rem;
  border-radius: 0.5rem;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-delete-row:hover {
  background-color: rgba(244, 63, 94, 0.1);
}

.status-msg {
  margin-top: 20px;
  color: #a1a1aa;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.spinner {
  width: 14px;
  height: 14px;
  border: 2px solid #52525b;
  border-top-color: #42b883;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* Custom Overlays Style */
.custom-notification {
  position: fixed;
  bottom: 20px;
  right: 20px;
  padding: 12px 24px;
  border-radius: 8px;
  color: white;
  font-weight: 600;
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  box-shadow: 0 4px 15px rgba(0,0,0,0.4);
  z-index: 1000;
  pointer-events: none;
}
.custom-notification.success {
  background-color: #10b981;
}
.custom-notification.error {
  background-color: #ef4444;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1100;
}

.modal-card {
  background: #222;
  border: 1px solid #333;
  padding: 24px;
  border-radius: 12px;
  width: 90%;
  max-width: 400px;
  text-align: center;
  box-shadow: 0 10px 25px rgba(0,0,0,0.6);
  font-family: 'Segoe UI', system-ui, sans-serif;
}

.modal-card h4 {
  margin-top: 0;
  color: #f3f4f6;
  font-size: 1.2rem;
  margin-bottom: 12px;
}

.modal-card p {
  color: #9ca3af;
  margin-bottom: 24px;
  font-size: 0.95rem;
}

.modal-actions {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.modal-actions button {
  flex: 1;
}

.btn-cancel {
  background: #374151;
  color: #d1d5db;
}
.btn-cancel:hover {
  background: #4b5563;
}

.btn-danger-confirm {
  background: #ef4444;
  color: white;
}
.btn-danger-confirm:hover {
  background: #dc2626;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: scale(0.95);
}

@keyframes blink { 50% { opacity: 0.6; } }
@keyframes spin { to { transform: rotate(360deg); } }
</style>