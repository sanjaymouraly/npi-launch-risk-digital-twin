import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Projects from './pages/Projects'
import ProjectOverview from './pages/ProjectOverview'
import SchedulePage from './pages/SchedulePage'
import RiskPage from './pages/RiskPage'
import SuppliersPage from './pages/SuppliersPage'
import MilestonesPage from './pages/MilestonesPage'
import SimulationPage from './pages/SimulationPage'
import ScenariosPage from './pages/ScenariosPage'
import OptimizationPage from './pages/OptimizationPage'
import AssistantPage from './pages/AssistantPage'
import DecisionsPage from './pages/DecisionsPage'
import MethodologyPage from './pages/MethodologyPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:projectId" element={<Navigate to="overview" replace />} />
        <Route path="/projects/:projectId/overview" element={<ProjectOverview />} />
        <Route path="/projects/:projectId/schedule" element={<SchedulePage />} />
        <Route path="/projects/:projectId/risks" element={<RiskPage />} />
        <Route path="/projects/:projectId/suppliers" element={<SuppliersPage />} />
        <Route path="/projects/:projectId/milestones" element={<MilestonesPage />} />
        <Route path="/projects/:projectId/simulation" element={<SimulationPage />} />
        <Route path="/projects/:projectId/scenarios" element={<ScenariosPage />} />
        <Route path="/projects/:projectId/optimization" element={<OptimizationPage />} />
        <Route path="/projects/:projectId/assistant" element={<AssistantPage />} />
        <Route path="/projects/:projectId/decisions" element={<DecisionsPage />} />
        <Route path="/projects/:projectId/methodology" element={<MethodologyPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
