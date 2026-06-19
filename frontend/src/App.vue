<template>
  <div class="timer-container">
    <h1>Python + Vue Timer</h1>
    
    <div class="input-group">
      <input v-model.number="seconds" type="number" placeholder="Enter seconds" />
      <button @click="startTimer">Start Timer</button>
    </div>

    <div v-if="loading">Connecting to backend...</div>
    
    <div v-if="timerData" class="result">
      <p>Status: <strong>{{ timerData.status }}</strong></p>
      <p>Duration: {{ timerData.duration }} seconds</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const seconds = ref(60)
const timerData = ref(null)
const loading = ref(false)

async function startTimer() {
  loading.value = true
  timerData.value = null
  try {
    const response = await fetch('http://localhost:8000/api/timer/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ duration_seconds: seconds.value })
    })
    timerData.value = await response.json()
  } catch (error) {
    console.error("Failed to connect:", error)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.timer-container { font-family: sans-serif; max-width: 400px; margin: 50px auto; text-align: center; }
.input-group { margin-bottom: 20px; }
input { padding: 8px; margin-right: 10px; }
button { padding: 8px 16px; background-color: #42b883; color: white; border: none; cursor: pointer; }
.result { margin-top: 20px; padding: 15px; border: 1px solid #ddd; background-color: #f9f9f9; }
</style>