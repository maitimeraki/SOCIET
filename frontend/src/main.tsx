import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// The Quiet Room faces. Fraunces (display) is the editorial serif — marketing headlines, page
// titles, the verdict's question, pull quotes. Archivo (ui) is the grotesque: app chrome, body
// copy, labels, buttons, tables. JetBrains Mono (mono) is every measurement. Spectral is retired:
// Archivo at 16/26 is more legible on screen, and the system stays at three families.
import '@fontsource-variable/fraunces'
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource-variable/jetbrains-mono'
// Sigma's inner `.sigma-container` gets its size from this sheet; without it the container has height 0
// and Sigma's constructor throws "Container has no height", unmounting the whole app.
import '@react-sigma/core/lib/style.css'
import './index.css'
import App from './App'
import AppErrorBoundary from './components/AppErrorBoundary'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppErrorBoundary>
      <App />
    </AppErrorBoundary>
  </StrictMode>,
)
