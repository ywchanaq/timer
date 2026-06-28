import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../../App.vue'

// Mock global fetch API
const fetchMock = vi.fn()
global.fetch = fetchMock

describe('Countdown Timer & Preset Suite', () => {
  beforeEach(() => {
    fetchMock.mockReset()
    vi.useFakeTimers()

    // Establish standard, safe default mock implementations for onMounted requests
    fetchMock.mockImplementation((url) => {
      if (url.includes('/api/timers')) {
        return Promise.resolve({
          ok: true,
          json: async () => []
        })
      }
      if (url.includes('/api/config/folder')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ folder_path: '' })
        })
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({})
      })
    })

    // --- MOCK LOCALSTORAGE ---
    let store = {}
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn((key) => store[key] || null),
        setItem: vi.fn((key, value) => { store[key] = value.toString() }),
        clear: vi.fn(() => { store = {} }),
        removeItem: vi.fn((key) => { delete store[key] })
      },
      writable: true,
      configurable: true
    })
  })

  // --- 1. INITIAL RENDERING & INPUT MAPPING TESTS ---

  it('renders the initial state correctly with padded zeros', () => {
    const wrapper = mount(App)
    const inputs = wrapper.findAll('input')
    
    // inputs[0] is Hours (number input)
    // inputs[1] is Minutes (text input with padded displayMinutes value)
    // inputs[2] is Seconds (text input with padded displaySeconds value)
    expect(inputs[1].element.value).toBe('00')
    expect(inputs[2].element.value).toBe('00')
  })

  it('renders "No stored presets found" message when local preset array is empty', async () => {
    const wrapper = mount(App)
    await vi.dynamicImportSettled() // Wait for fetch in onMounted
    
    const emptyMsg = wrapper.find('.empty-msg')
    expect(emptyMsg.exists()).toBe(true)
    expect(emptyMsg.text()).toContain('No stored presets found.')
  })

  // --- 2. KEYBOARD AND INPUT MANIPULATION TESTS ---

  it('enforces the strict character replacement overwrite rule', async () => {
    const wrapper = mount(App)
    const secondsInput = wrapper.findAll('input')[2]

    // Simulate typing '0', then '8' to set the state to "08"
    await secondsInput.trigger('keydown', { key: '0' })
    await secondsInput.trigger('keydown', { key: '8' })
    expect(secondsInput.element.value).toBe('08')
    
    // Simulate typing '6' immediately after -> "08" + "6" becomes "086"
    // The slice(-2) turns it into "86". Since 86 > 59, it drops to "06"
    await secondsInput.trigger('keydown', { key: '6' })
    expect(secondsInput.element.value).toBe('06')
  })

  it('handles backspace by dividing the value by 10', async () => {
    const wrapper = mount(App)
    const minutesInput = wrapper.findAll('input')[1]

    // Set value to 25
    await minutesInput.trigger('keydown', { key: '2' })
    await minutesInput.trigger('keydown', { key: '5' })
    expect(minutesInput.element.value).toBe('25')
    
    // Trigger backspace
    await minutesInput.trigger('keydown', { key: 'Backspace' })
    expect(minutesInput.element.value).toBe('02')
  })

  it('blocks non-numeric keys from modifying minutes or seconds', async () => {
    const wrapper = mount(App)
    const secondsInput = wrapper.findAll('input')[2]

    // Set a baseline
    await secondsInput.trigger('keydown', { key: '1' })
    expect(secondsInput.element.value).toBe('01')

    // Try typing an alphabetical key 'a' (should be blocked and value unmodified)
    await secondsInput.trigger('keydown', { key: 'a' })
    expect(secondsInput.element.value).toBe('01')
  })

  // --- 3. STATE AND COMPUTED CALCULATION TESTS ---

  it('correctly calculates formatted Time computed properties', () => {
    const wrapper = mount(App)

    // Set time inside input state variables
    wrapper.vm.inputHours = 1
    wrapper.vm.minutesVal = 5
    wrapper.vm.secondsVal = 9

    // Direct access helper test
    expect(wrapper.vm.displayMinutes).toBe('05')
    expect(wrapper.vm.displaySeconds).toBe('09')
  })

  // --- 4. PRESETS CRUD & USER FLOW TESTS ---

  it('shows an error notification banner if trying to save an empty setup name', async () => {
    const wrapper = mount(App)
    
    // Attempt to store timer without setting input label
    wrapper.vm.timerLabel = ''
    await wrapper.find('.btn-save').trigger('click')

    // Confirm that our custom notifications rendered in DOM
    const notification = wrapper.find('.custom-notification')
    expect(notification.exists()).toBe(true)
    expect(notification.text()).toContain('Please name your timer')
  })

  it('sends post request to API upon saving a valid configuration', async () => {
    const wrapper = mount(App)
    
    // Fill up state details
    wrapper.vm.timerLabel = 'Pomodoro Test'
    wrapper.vm.inputHours = 0
    wrapper.vm.minutesVal = 25
    wrapper.vm.secondsVal = 0

    await wrapper.find('.btn-save').trigger('click')

    // Assert fetch endpoint was called with correct body parser
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/timers', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        label: 'Pomodoro Test',
        duration_seconds: 1500
      })
    }))
  })

  it('loads preset values correctly into timer displays when clicked', async () => {
    fetchMock.mockImplementation((url) => {
      if (url.includes('/api/timers')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 10, label: 'Sprint Core', duration_seconds: 3665 } // 1h 1m 5s
          ]
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const wrapper = mount(App)
    await vi.dynamicImportSettled() // Wait for fetch onMounted hook
    
    // Trigger the click event on list row
    await wrapper.find('.timers-list li').trigger('click')

    expect(wrapper.vm.inputHours).toBe(1)
    expect(wrapper.vm.minutesVal).toBe(1)
    expect(wrapper.vm.secondsVal).toBe(5)
  })

  it('triggers delete confirmation modal and cancels correctly', async () => {
    fetchMock.mockImplementation((url) => {
      if (url.includes('/api/timers')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 42, label: 'Test Target', duration_seconds: 120 }
          ]
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const wrapper = mount(App)
    await vi.dynamicImportSettled()

    // Trigger delete button
    await wrapper.find('.btn-delete-row').trigger('click')

    // Confirm Modal is visible
    expect(wrapper.vm.confirmModal.show).toBe(true)
    expect(wrapper.vm.confirmModal.message).toContain('Test Target')

    // Click cancel button on modal
    await wrapper.find('.btn-cancel').trigger('click')
    expect(wrapper.vm.confirmModal.show).toBe(false)
    expect(fetchMock).not.toHaveBeenCalledWith('http://localhost:8000/api/timers/42', expect.any(Object))
  })

  it('triggers delete confirmation modal and deletes preset on confirm', async () => {
    fetchMock.mockImplementation((url) => {
      if (url.includes('/api/timers')) {
        return Promise.resolve({
          ok: true,
          json: async () => [
            { id: 42, label: 'Test Target', duration_seconds: 120 }
          ]
        })
      }
      return Promise.resolve({ ok: true, json: async () => ({}) })
    })

    const wrapper = mount(App)
    await vi.dynamicImportSettled()

    // Trigger delete button
    await wrapper.find('.btn-delete-row').trigger('click')

    // Click confirm delete on modal
    await wrapper.find('.btn-danger-confirm').trigger('click')
    expect(wrapper.vm.confirmModal.show).toBe(false)

    // Verify DELETE request was issued
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/timers/42', expect.objectContaining({
      method: 'DELETE'
    }))
  })

  // --- 5. TIMER TICKING & LIVE LIFECYCLE TESTS ---

  it('starts countdown timer and preloads alert at 10 seconds remaining', async () => {
    fetchMock.mockImplementation((url) => {
      if (url.includes('/api/timer/start')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ duration: 12 })
        })
      }
      if (url.includes('/api/config/folder')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ folder_path: 'C:\\MockAudio' })
        })
      }
      if (url.includes('/api/alert/preload-backend')) {
        return Promise.resolve({ ok: true, json: async () => ({ status: 'preloaded' }) })
      }
      if (url.includes('/api/alert/play-backend')) {
        return Promise.resolve({ ok: true, json: async () => ({ status: 'playing', file: 'alarm.mp3' }) })
      }
      return Promise.resolve({ ok: true, json: async () => [] })
    })

    const wrapper = mount(App)
    wrapper.vm.inputHours = 0
    wrapper.vm.minutesVal = 0
    wrapper.vm.secondsVal = 12
    wrapper.vm.alertFolder = 'C:\\MockAudio'

    await wrapper.find('.btn-start').trigger('click')
    await vi.dynamicImportSettled()

    expect(wrapper.vm.isRunning).toBe(true)
    expect(wrapper.vm.timeLeft).toBe(12)

    // Advance 2 seconds -> Time left: 10. Should trigger preload
    await vi.advanceTimersByTimeAsync(2000)
    expect(wrapper.vm.timeLeft).toBe(10)
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/alert/preload-backend', { method: 'POST' })

    // Advance 10 more seconds -> Time left: 0. Should trigger play
    await vi.advanceTimersByTimeAsync(10000)
    expect(wrapper.vm.timeLeft).toBe(0)
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/alert/play-backend', { method: 'POST' })
  })

  it('resets timer active state and triggers backend stop signal on reset', async () => {
    fetchMock.mockImplementation((url) => {
      if (url.includes('/api/timer/start')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ duration: 10 })
        })
      }
      return Promise.resolve({ ok: true, json: async () => [] })
    })

    const wrapper = mount(App)
    wrapper.vm.inputHours = 0
    wrapper.vm.minutesVal = 0
    wrapper.vm.secondsVal = 10

    await wrapper.find('.btn-start').trigger('click')
    await vi.dynamicImportSettled()

    // Trigger reset
    await wrapper.find('.btn-reset').trigger('click')
    
    expect(wrapper.vm.isRunning).toBe(false)
    expect(wrapper.vm.timeLeft).toBe(0)
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/alert/stop-backend', { method: 'POST' })
  })

  // --- 6. FOLDER PICKER & MANUAL PATH CONFIG TESTS ---

  it('toggles configuration UI modes and saves manual path correctly', async () => {
    const wrapper = mount(App)

    // Toggle to manual path input mode
    await wrapper.find('.mode-toggle button:last-child').trigger('click')
    expect(wrapper.vm.configMode).toBe('path')

    // Set path and trigger change
    wrapper.vm.alertFolder = '/var/alerts/'
    await wrapper.find('.folder-input').trigger('change')

    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/config/folder', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: '/var/alerts/' })
    }))
  })

})