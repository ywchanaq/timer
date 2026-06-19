import { mount } from '@vue/test-utils'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import App from '../../App.vue'

describe('Timer App Frontend Logic', () => {
  let wrapper

  beforeEach(() => {
    wrapper = mount(App)
    // Mock global fetch for API calls
    global.fetch = vi.fn()
  })

  it('renders the initial state correctly with padded zeros', () => {
    const inputs = wrapper.findAll('input')
    expect(inputs[1].element.value).toBe('00') // Minutes
    expect(inputs[2].element.value).toBe('00') // Seconds
  })

  it('enforces the strict character replacement overwrite rule', async () => {
    const secondsInput = wrapper.findAll('input')[2]

    // Simulate typing '0', then '8' to set the state to "08"
    await secondsInput.trigger('keydown', { key: '0' })
    await secondsInput.trigger('keydown', { key: '8' })
    
    // Simulate typing '6' immediately after -> "08" + "6" becomes "086"
    // The slice(-2) turns it into "86". Since 86 > 59, it should drop to "06"
    await secondsInput.trigger('keydown', { key: '6' })

    expect(secondsInput.element.value).toBe('06')
  })

  it('handles backspace by dividing the value by 10', async () => {
    const minutesInput = wrapper.findAll('input')[1]

    // Set value to 25
    await minutesInput.trigger('keydown', { key: '2' })
    await minutesInput.trigger('keydown', { key: '5' })
    
    // Trigger backspace
    await minutesInput.trigger('keydown', { key: 'Backspace' })
    
    expect(minutesInput.element.value).toBe('02')
  })
})