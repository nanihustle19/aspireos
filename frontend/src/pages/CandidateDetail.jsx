import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, errMsg } from "@/lib/api";
import { InlineError, Loading } from "@/components/Common";
import { StatusBadge } from "@/components/StatusBadge";
import { CandidateActions } from "@/components/CandidateActions";
import { OverviewTab, TimelineTab } from "@/components/CandidateOverview";
import { NotesTab, TasksTab, DocumentsTab, AuditTab } from "@/components/CandidateTabs";
import { PipelineTab } from "@/pages/Pipeline";
import { useAuth } from "@/context/AuthContext";

export default function CandidateDetail() {
  const { id } = useParams();
  const { isOps, isAuditor, role } = useAuth();
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState("");
  const [tick, setTick] = useState(0);
  const load = useCallback(() => {
    api.get(`/candidates/${id}`).then((r) => { setDetail(r.data); setError(""); setTick((t) => t + 1); }).catch((e) => setError(errMsg(e)));
  }, [id]);
  useEffect(() => { load(); }, [load]);
  if (error) return <div className="space-y-3"><InlineError error={error} testId="candidate-detail-error" /><Link to="/candidates" className="text-sm text-indigo-700 hover:underline">Back to candidates</Link></div>;
  if (!detail) return <Loading />;
  const c = detail.candidate;
  const canWrite = role !== "AUDITOR" && (detail.permissions.edit_level !== null);
  return (
    <div data-testid="candidate-detail-page">
      <Link to="/candidates" className="mb-3 inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-900"><ArrowLeft className="h-3 w-3" />Candidates</Link>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-4 rounded-md border bg-white p-4 fade-up">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 data-testid="candidate-name" className="text-2xl font-bold tracking-tight">{c.full_name}</h1>
            <StatusBadge status={c.status} testId="candidate-status-badge" />
          </div>
          <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600">
            <span>{c.primary_skill}</span>
            <span data-testid="candidate-current-group">Group: <b className="text-slate-900">{detail.group?.name || "Unassigned"}</b></span>
            <span data-testid="candidate-owner">Owner: <b className="text-slate-900">{detail.owner?.name || "—"}</b></span>
            <span className="font-mono text-[11px] text-slate-400" data-testid="candidate-version">v{c.version}</span>
          </div>
        </div>
        {!isAuditor && <CandidateActions detail={detail} reload={load} />}
      </div>
      <Tabs defaultValue="overview" data-testid="candidate-detail-tabs">
        <TabsList className="bg-white border">
          {["overview", "pipeline", "timeline", "notes", "tasks", "documents"].map((t) => <TabsTrigger key={t} value={t} data-testid={`tab-${t}`} className="capitalize">{t}</TabsTrigger>)}
          {(isOps || isAuditor) && <TabsTrigger value="audit" data-testid="tab-audit">Audit</TabsTrigger>}
        </TabsList>
        <TabsContent value="overview"><OverviewTab detail={detail} reload={load} isOps={isOps} /></TabsContent>
        <TabsContent value="pipeline"><PipelineTab detail={detail} reload={load} /></TabsContent>
        <TabsContent value="timeline"><TimelineTab cid={id} key={tick} /></TabsContent>
        <TabsContent value="notes"><NotesTab cid={id} canWrite={role !== "AUDITOR"} /></TabsContent>
        <TabsContent value="tasks"><TasksTab cid={id} canWrite={role !== "AUDITOR"} /></TabsContent>
        <TabsContent value="documents"><DocumentsTab cid={id} canUpload={canWrite} /></TabsContent>
        {(isOps || isAuditor) && <TabsContent value="audit"><AuditTab cid={id} key={tick} /></TabsContent>}
      </Tabs>
    </div>
  );
}
