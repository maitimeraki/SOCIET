import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// The Survey faces. Archivo (titling) is loaded from the wdth axis file so the design can
// reach the wide weights as well as the full weight range; Spectral (record) has no variable
// build, so the static 400/500/600 + italic are used; JetBrains Mono (measurement) is variable.
import '@fontsource-variable/archivo/wdth.css'
import '@fontsource/spectral/400.css'
import '@fontsource/spectral/500.css'
import '@fontsource/spectral/600.css'
import '@fontsource/spectral/400-italic.css'
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
