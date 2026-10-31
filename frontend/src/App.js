import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import { Loading } from "@/components/Common";
import Login from "@/pages/Login";
import Activate from "@/pages/Activate";
import AuthCallback from "@/pages/AuthCallback";
import Dashboard from "@/pages/Dashboard";
import Candidates from "@/pages/Candidates";
import CandidateWizard from "@/pages/CandidateWizard";
import CandidateDetail from "@/pages/CandidateDetail";
import Bench from "@/pages/Bench";
import Marketing from "@/pages/Marketing";
import { Submissions, Interviews, Offers, Placements } from "@/pages/Pipeline";
import Directory from "@/pages/Directory";
import Groups from "@/pages/Groups";
import GroupDetail from "@/pages/GroupDetail";
import UsersPage from "@/pages/Users";
import Tasks from "@/pages/Tasks";
import Reports from "@/pages/Reports";
import AuditLog from "@/pages/AuditLog";
import DataJobs from "@/pages/DataJobs";
import SettingsPage from "@/pages/Settings";
import Organizations from "@/pages/Organizations";
import { ForgotPassword, ResetPassword } from "@/pages/PasswordReset";

function Protected({ children }) {
  const { session } = useAuth();
  if (session === null) return <Loading />;
  if (session === false) return <Navigate to="/login" replace />;
  return children;
}

function AppRouter() {
  const location = useLocation();
  if (location.hash?.includes("session_id=")) return <AuthCallback />;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/activate" element={<Activate />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<Protected><Layout /></Protected>}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/candidates" element={<Candidates />} />
        <Route path="/candidates/new" element={<CandidateWizard />} />
        <Route path="/candidates/:id" element={<CandidateDetail />} />
        <Route path="/bench" element={<Bench />} />
        <Route path="/marketing" element={<Marketing />} />
        <Route path="/submissions" element={<Submissions />} />
        <Route path="/interviews" element={<Interviews />} />
        <Route path="/offers" element={<Offers />} />
        <Route path="/placements" element={<Placements />} />
        <Route path="/jobs" element={<Directory entity="jobs" />} />
        <Route path="/clients" element={<Directory entity="clients" />} />
        <Route path="/vendors" element={<Directory entity="vendors" />} />
        <Route path="/groups" element={<Groups />} />
        <Route path="/groups/:id" element={<GroupDetail />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/audit" element={<AuditLog />} />
        <Route path="/data" element={<DataJobs />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/organizations" element={<Organizations />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <AuthProvider>
          <AppRouter />
          <Toaster position="bottom-right" richColors />
        </AuthProvider>
      </BrowserRouter>
    </div>
  );
}
