import { motion, useReducedMotion } from 'framer-motion'
import type { QueryIntent } from '../../run/events'
import Chip from '../ui/Chip'
import { ruleClasses } from '../ui/Rule'

export default function IntentCard({ intent, question }: { intent: QueryIntent; question: string }) {
  const reduced = useReducedMotion()
  return (
    <div className={`${ruleClasses('top')} pt-4`}>
      <p className="font-ui text-[20px] leading-[28px] text-ink">{question}</p>
      <p className="tnum mt-1 font-mono text-mono text-accent">reading as: {intent.core_question}</p>
      <motion.div
        className="mt-3 flex flex-wrap gap-1.5"
        initial={false}
        animate="show"
        variants={{ show: { transition: { staggerChildren: reduced ? 0 : 0.04 } } }}
      >
        {intent.direct_keywords.map((keyword) => (
          <motion.span
            key={keyword}
            variants={reduced ? undefined : { hidden: { opacity: 0, y: 4 }, show: { opacity: 1, y: 0 } }}
            transition={{ duration: 0.15, ease: [0.2, 0, 0, 1] }}
          >
            <Chip>{keyword}</Chip>
          </motion.span>
        ))}
      </motion.div>
      <p className="mt-3 text-micro text-ink-3">
        sectors: {intent.latent_sectors.join(' · ') || '—'} · perspectives: {intent.search_perspectives.join(' · ') || '—'}
      </p>
    </div>
  )
}
