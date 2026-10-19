"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ErrorState, StatusBadge } from "@/components/common";
import { ShareDialog } from "@/components/project/share-dialog";
import { ActivityTab } from "@/components/project/activity-tab";
import { ActualsTab } from "@/components/project/actuals-tab";
import { EstimateTab } from "@/components/estimate/estimate-tab";
import { OverviewTab } from "@/components/project/overview-tab";
import { QuestionsTab } from "@/components/project/questions-tab";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useEstimates, useProject } from "@/hooks/queries";

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const { data: project, isLoading, error } = useProject(id);
  const { data: estimates } = useEstimates(id);
  const [tab, setTab] = useState("overview");
  const [estimateId, setEstimateId] = useState<string | null>(null);
  const [agentRequest, setAgentRequest] = useState(0);

  useEffect(() => {
    if (!estimateId && estimates?.length) {
      const final = estimates.find((e) => e.status === "final");
      // eslint-disable-next-line react-hooks/set-state-in-effect -- default selection once data arrives
      setEstimateId((final ?? estimates[0]).id);
    }
  }, [estimates, estimateId]);

  if (error) return <ErrorState error={error} />;
  if (isLoading || !project) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold tracking-tight">{project.name}</h1>
        <StatusBadge status={project.status} />
        {project.client_name && <span className="text-sm text-muted-foreground">· {project.client_name}</span>}
        {project.access === "owner" && !project.is_archive && (
          <div className="ml-auto">
            <ShareDialog project={project} />
          </div>
        )}
      </div>
      <Tabs value={tab} onValueChange={(v) => setTab(String(v))}>
        <TabsList>
          <TabsTrigger value="overview">Overview & Documents</TabsTrigger>
          <TabsTrigger value="estimate">Estimate</TabsTrigger>
          <TabsTrigger value="questions">Questions & Risks</TabsTrigger>
          <TabsTrigger value="actuals">Actuals</TabsTrigger>
          <TabsTrigger value="activity">Activity</TabsTrigger>
        </TabsList>
        <TabsContent value="overview" className="pt-3">
          <OverviewTab
            project={project}
            onGenerated={(eid) => {
              setEstimateId(eid);
              setTab("estimate");
              setAgentRequest((n) => n + 1);
            }}
          />
        </TabsContent>
        <TabsContent value="estimate" className="pt-3">
          <EstimateTab
            projectId={id}
            estimates={estimates ?? []}
            estimateId={estimateId}
            onSelect={setEstimateId}
            agentRequest={agentRequest}
          />
        </TabsContent>
        <TabsContent value="questions" className="pt-3">
          <QuestionsTab estimateId={estimateId} />
        </TabsContent>
        <TabsContent value="actuals" className="pt-3">
          <ActualsTab project={project} estimates={estimates ?? []} />
        </TabsContent>
        <TabsContent value="activity" className="pt-3">
          <ActivityTab estimateId={estimateId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
