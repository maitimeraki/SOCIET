import type { HTMLAttributes } from 'react'

/**
 * §8.3 / §6.4 — a card is **an object the customer picks up**: paper, a 16px corner, 24px of
 * space inside, and one soft shadow. It carries no border: a card carries a shadow and no rule,
 * a record carries a rule and no shadow. Never both — so this primitive has no border, ever.
 *
 * The defaults are the Quiet Room card. `pad` and `radius` remain as overrides, and `hover`
 * lifts the object one step when the pointer arrives.
 */
export type CardElement = 'div' | 'article' | 'li' | 'section'

export type CardProps = {
  as?: CardElement
  /** The space inside the card, in pixels. */
  pad?: 16 | 24 | 32
  radius?: 'md' | 'lg'
  /** Lifts the object on hover — the floating shadow. */
  hover?: boolean
} & HTMLAttributes<HTMLElement>

export default function Card({
  as = 'div',
  pad = 24,
  radius = 'lg',
  hover = false,
  className = '',
  children,
  ...rest
}: CardProps) {
  const classes = [
    'bg-paper',
    pad === 32 ? 'p-8' : pad === 24 ? 'p-6' : 'p-4',
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
