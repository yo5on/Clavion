import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import OwnerAccess from './components/OwnerAccess'
import CaseView from './pages/CaseView'
import Cases from './pages/Cases'
import Dashboard from './pages/Dashboard'
import NewAudit from './pages/NewAudit'
import NotYetAvailable from './pages/NotYetAvailable'
import { ToastProvider } from './components/ui'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter basename={import.meta.env.BASE_URL}>
      <ToastProvider>
      <OwnerAccess>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="audit/new" element={<NewAudit />} />
          <Route path="cases" element={<Cases />} />
          <Route path="cases/:id" element={<CaseView />} />
          <Route path="*" element={<NotYetAvailable title="Page not found" body="This page does not exist." />} />
        </Route>
      </Routes>
      </OwnerAccess>
      </ToastProvider>
    </BrowserRouter>
  </StrictMode>,
)
