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
  })

  // --- 1. INITIAL RENDERING & INPUT MAPPING TESTS ---

  it('renders the initial state correctly with padded zeros', () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })
    
    const wrapper = mount(App)
    const inputs = wrapper.findAll('input')
    
    // inputs[0] is Hours (number input)
    // inputs[1] is Minutes (text input with padded displayMinutes value)
    // inputs[2] is Seconds (text input with padded displaySeconds value)
    expect(inputs[1].element.value).toBe('00')
    expect(inputs[2].element.value).toBe('00')
  })

  it('renders "No stored presets found" message when local preset array is empty', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

    const wrapper = mount(App)
    await vi.dynamicImportSettled() // Wait for fetch in onMounted
    
    const emptyMsg = wrapper.find('.empty-msg')
    expect(emptyMsg.exists()).toBe(true)
    expect(emptyMsg.text()).toContain('No stored presets found.')
  })

  // --- 2. KEYBOARD AND INPUT MANIPULATION TESTS ---

  it('enforces the strict character replacement overwrite rule', async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

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

  // --- 3. STATE AND COMPUTED CALCULATION TESTS ---

  it('correctly calculates formatted Time computed properties', () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => []
    })

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
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => []
    })

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
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        { id: 10, label: 'Sprint Core', duration_seconds: 3665 } // 1h 1m 5s
      ]
    })

    const wrapper = mount(App)
    await vi.dynamicImportSettled() // Wait for fetch onMounted hook
    
    // Trigger the click event on list row
    await wrapper.find('.timers-list li').trigger('click')

    expect(wrapper.vm.inputHours).toBe(1)
    expect(wrapper.vm.minutesVal).toBe(1)
    expect(wrapper.vm.secondsVal).toBe(5)
  })
})