import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import NotYetAvailable from './pages/NotYetAvailable'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route
            path="audit/new"
            element={<NotYetAvailable title="New audit" body="Document upload and extraction arrive in Phase 2." />}
          />
          <Route
            path="cases"
            element={<NotYetAvailable title="Case history" body="Saved audits will appear here once analysis is available." />}
          />
          <Route path="*" element={<NotYetAvailable title="Page not found" body="This page does not exist." />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
