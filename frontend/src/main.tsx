import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/newsreader'
import '@fontsource-variable/public-sans'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
// Sigma's inner `.sigma-container` gets its size from this sheet; without it the container has height 0
// and Sigma's constructor throws "Container has no height", unmounting the whole app.
import '@react-sigma/core/lib/style.css'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
