import type { HTMLAttributes } from 'react'

/**
 * §14.1 — a card is **an object the customer picks up**: the canvas, one soft shadow, and no
 * border at all. House style rule 5: a card carries a shadow and no rule, a record carries a
 * rule and no shadow. Never both, never neither — so this primitive has no border, ever.
 *
 * `pad` is the space inside the card, `radius` the corner, and `hover` lifts the object one
 * step when the pointer arrives. Everything else is a class the caller may add.
 */
export type CardElement = 'div' | 'article' | 'li' | 'section'

export type CardProps = {
  as?: CardElement
  /** The space inside the card, in pixels. */
  pad?: 16 | 24
  radius?: 'md' | 'lg'
  /** Lifts the object on hover — the floating shadow. */
  hover?: boolean
} & HTMLAttributes<HTMLElement>

export default function Card({
  as = 'div',
  pad = 16,
  radius = 'md',
  hover = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  const classes = [
    'bg-paper',
    pad === 24 ? 'p-6' : 'p-4',
    'shadow-card',
    radius === 'lg' ? 'rounded-lg' : 'rounded-md',
    hover ? 'transition-[box-shadow,transform] duration-state hover:-translate-y-px hover:shadow-sheet' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  if (as === 'article') {
    return (
      <article className={classes} {...rest}>
        {children}
      </article>
    )
  }
  if (as === 'li') {
    return (
      <li className={classes} {...rest}>
        {children}
      </li>
    )
  }
  if (as === 'section') {
    return (
      <section className={classes} {...rest}>
        {children}
      </section>
    )
  }
  return (
    <div className={classes} {...rest}>
      {children}
    </div>
  )
}
