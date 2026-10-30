import { describe, expect, it } from 'vitest'
import { buttonClasses } from './Button'

describe('the Quiet Room buttons', () => {
  it('fills the primary with a flat evergreen, never a ramp', () => {
    expect(buttonClasses('primary')).toContain('action-fill')
    expect(buttonClasses('primary')).not.toContain('gradient')
  })

  it('gives every variant the 12px radius', () => {
    for (const variant of ['primary', 'secondary', 'ghost', 'danger'] as const) {
      expect(buttonClasses(variant), variant).toContain('rounded-md')
    }
  })

  it('drops the corner registration tick the old world drew', () => {
    expect(buttonClasses('secondary')).not.toContain('after:border-r')
  })

  it('rules the ghost underline in the record rule, never the decorative hairline', () => {
    expect(buttonClasses('ghost')).toContain('decoration-rule')
    expect(buttonClasses('ghost')).not.toContain('decoration-hairline')
  })

  it('keeps the 44px touch target below 640px', () => {
    expect(buttonClasses('primary')).toContain('max-sm:min-h-11')
  })
})
