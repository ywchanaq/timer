<template>
  <div class="timer-container">
    <h1>Python + Vue Timer</h1>
    
    <div v-if="!isRunning" class="input-form">
      <div class="input-row">
        <div class="input-group">
          <label>HH</label>
          <input v-model.number="inputHours" type="number" min="0" max="23" placeholder="00" />
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

    <div v-else class="ticker-screen">
      <div class="countdown-display" :class="{ 'time-up': timeLeft === 0 }">
        {{ formattedTime }}
      </div>
      <button @click="resetTimer" class="btn-reset">Reset</button>
    </div>

    <div v-if="loading" class="status-msg">Connecting to backend...</div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'

// Hours remains a standard reactive number
const inputHours = ref(0)

// Minutes and Seconds store raw values for sliding logic
const minutesVal = ref(0)
const secondsVal = ref(0)

const timeLeft = ref(0)
const isRunning = ref(false)
const loading = ref(false)
let timerInterval = null

// Pad sliding inputs to 2 digits
const displayMinutes = computed(() => String(minutesVal.value).padStart(2, '0'))
const displaySeconds = computed(() => String(secondsVal.value).padStart(2, '0'))

// Live countdown format (HH:MM:SS)
const formattedTime = computed(() => {
  const hours = Math.floor(timeLeft.value / 3600)
  const minutes = Math.floor((timeLeft.value % 3600) / 60)
  const seconds = timeLeft.value % 60
  
  return [
    String(hours).padStart(2, '0'),
    String(minutes).padStart(2, '0'),
    String(seconds).padStart(2, '0')
  ].join(':')
})

// Windows Timer sliding logic applied only to MM and SS
function handleKeyDown(type, event) {
  const key = event.key
  const targetRef = type === 'minutes' ? minutesVal : secondsVal

  if (['Backspace', 'Delete', 'Tab', 'ArrowLeft', 'ArrowRight'].includes(key)) {
    if (key === 'Backspace') {
      event.preventDefault()
      targetRef.value = Math.floor(targetRef.value / 10)
      // Reset back to first press state if cleared
      if (targetRef.value === 0) {
        isFirstPress[type] = true
      }
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

  if (display_value> 59){
    display_value = key
  }

  // Convert back to a number for your backend logic
  targetRef.value = display_value
}

async function startTimer() {
  // Combine Hours (unchanged) + Sliding Minutes + Sliding Seconds
  const totalSeconds = (inputHours.value * 3600) + (minutesVal.value * 60) + secondsVal.value
  
  if (totalSeconds <= 0) {
    alert("Please enter a valid time duration.")
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
      alert(data.detail || "Failed to start timer")
    }
  } catch (error) {
    console.error("Failed to connect to backend:", error)
    alert("Backend server is offline!")
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
.timer-container {
  font-family: 'Courier New', Courier, monospace;
  max-width: 450px;
  margin: 100px auto;
  text-align: center;
  background: #222;
  color: #fff;
  padding: 30px;
  border-radius: 12px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.3);
}

h1 {
  font-size: 1.5rem;
  color: #888;
  margin-bottom: 30px;
}

.input-row {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 30px;
}

.input-group {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.input-group label {
  font-size: 0.8rem;
  color: #666;
  margin-bottom: 5px;
}

.input-group input {
  background: #333;
  border: 1px solid #444;
  color: #fff;
  padding: 12px;
  border-radius: 6px;
  width: 75px;
  font-size: 1.6rem;
  text-align: center;
}

/* Specific styling for the sliding text inputs to drop the cursor */
input[type="text"] {
  caret-color: transparent;
}

.input-group input:focus {
  outline: none;
  border-color: #42b883;
}

/* Standard scrollbars removal for the numeric HH input */
.input-group input::-webkit-outer-spin-button,
.input-group input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.separator {
  font-size: 1.8rem;
  font-weight: bold;
  color: #444;
  margin: 20px 8px 0 8px;
}

button {
  padding: 12px 30px;
  background-color: #42b883;
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 1.1rem;
  cursor: pointer;
  font-weight: bold;
}

button:hover {
  background-color: #3aa876;
}

.countdown-display {
  font-size: 4.5rem;
  font-weight: bold;
  color: #42b883;
  margin-bottom: 20px;
  letter-spacing: 2px;
}

.countdown-display.time-up {
  color: #ff5252;
  animation: blink 1s infinite;
}

.btn-reset {
  background-color: #555;
}
.btn-reset:hover {
  background-color: #666;
}

.status-msg {
  margin-top: 15px;
  color: #aaa;
  font-size: 0.9rem;
}

@keyframes blink {
  50% { opacity: 0.5; }
}
</style>