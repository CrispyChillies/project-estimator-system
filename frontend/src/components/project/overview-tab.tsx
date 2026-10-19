"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ClipboardPaste, FileText, Sparkles, Trash2, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { EmptyState, JobProgress } from "@/components/common";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { errorToast, qk, useChunks, useDocuments } from "@/hooks/queries";
import { api } from "@/lib/api";
import { date } from "@/lib/format";
import type { DocumentOut, Job, Project } from "@/lib/types";
import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.md,.txt";

function ChunkViewer({ doc }: { doc: DocumentOut }) {
  const { data } = useChunks(doc.id);
  return (
    <ScrollArea className="h-64 rounded-md border">
      <div className="space-y-3 p-3">
        {data?.map((c) => (
          <div key={c.id} className="text-xs">
            <div className="mb-1 font-mono text-muted-foreground">chunk #{c.idx + 1}</div>
            <pre className="font-sans whitespace-pre-wrap">{c.text}</pre>
          </div>
        ))}
      </div>
    </ScrollArea>
  );
}

function GenerateDialog({ project, docs, onGenerated }: { project: Project; docs: DocumentOut[]; onGenerated: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const [learning, setLearning] = useState(true);
  const [selected, setSelected] = useState<string[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const qc = useQueryClient();
  const start = useMutation({
    mutationFn: () =>
      api<Job>(`/projects/${project.id}/estimates/generate`, {
        method: "POST",
        json: { learning, document_ids: selected.length ? selected : docs.map((d) => d.id) },
      }),
    onSuccess: (j) => setJobId(j.id),
    onError: errorToast,
  });
  const finished = (job: Job) => {
    if (job.status === "done" && job.result_ref) {
      toast.success(`Estimate generated (${learning ? "with" : "without"} learning)`);
      void qc.invalidateQueries({ queryKey: qk.estimates(project.id) });
      void qc.invalidateQueries({ queryKey: ["projects"] });
      onGenerated(job.result_ref);
      setOpen(false);
    } else if (job.status === "failed") toast.error(job.error ?? "Generation failed");
    setJobId(null);
  };
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button disabled={!docs.length} />}>
        <Sparkles /> Generate estimate
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Generate estimate</DialogTitle>
          <DialogDescription>
            Extract requirements, decompose into tasks, estimate hours ({"K"} samples) and — with learning on — calibrate
            with history and analogs.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <Label htmlFor="learning">Use learning</Label>
              <p className="text-xs text-muted-foreground">Off = pure LLM baseline through the same pipeline.</p>
            </div>
            <Switch id="learning" checked={learning} onCheckedChange={setLearning} />
          </div>
          <div className="space-y-2">
            <Label>Documents (none selected = all)</Label>
            {docs.map((d) => (
              <label key={d.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={selected.includes(d.id)}
                  onCheckedChange={(c) => setSelected((s) => (c ? [...s, d.id] : s.filter((x) => x !== d.id)))}
                />
                {d.filename}
              </label>
            ))}
          </div>
          {jobId && <JobProgress jobId={jobId} onDone={finished} />}
        </div>
        <DialogFooter>
          <Button onClick={() => start.mutate()} disabled={!!jobId || start.isPending}>
            Generate {learning ? "with" : "without"} learning
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const EXAMPLE_BRIEF = `Field service app for an HVAC maintenance company

Goals
- Customers book maintenance visits online and see technician arrival windows.
- Dispatchers plan daily routes for 25 technicians and reassign jobs when someone is sick.
- Technicians use a mobile app (offline capable) to see jobs, record parts used and capture a customer signature.

Integrations
- Existing accounting system (invoices are created there), via its REST API.
- SMS reminders the day before a visit.

Constraints
- Web back office plus iOS and Android apps.
- Single sign-on for staff with Microsoft 365.
- Go live before the winter season (about 4 months).`;

function PasteDialog({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("pasted-brief");
  const [text, setText] = useState("");
  const qc = useQueryClient();
  const paste = useMutation({
    mutationFn: () => api<DocumentOut>(`/projects/${projectId}/documents/paste`, { method: "POST", json: { title, text } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.documents(projectId) });
      setOpen(false);
      setText("");
      toast.success("Text added");
    },
    onError: errorToast,
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" />}>
        <ClipboardPaste /> Paste text
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Paste brief / notes</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          <Textarea rows={14} value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste client notes…" aria-label="Brief text" />
          <button type="button" className="text-xs text-primary underline underline-offset-4" onClick={() => setText(EXAMPLE_BRIEF)}>
            Paste an example brief
          </button>
        </div>
        <DialogFooter>
          <Button onClick={() => paste.mutate()} disabled={text.trim().length < 20 || paste.isPending}>
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function OverviewTab({ project, onGenerated }: { project: Project; onGenerated: (id: string) => void }) {
  const { data: docs } = useDocuments(project.id);
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        await api<DocumentOut>(`/projects/${project.id}/documents`, { method: "POST", body: fd });
      }
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.documents(project.id) });
      toast.success("Uploaded and parsed");
    },
    onError: errorToast,
  });
  const remove = useMutation({
    mutationFn: (id: string) => api<void>(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: qk.documents(project.id) }),
    onError: errorToast,
  });

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Documents</CardTitle>
          <CardDescription>PDF, DOCX, MD or TXT. Client documents are sent to the configured LLM provider.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              upload.mutate(Array.from(e.dataTransfer.files));
            }}
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-8 text-sm text-muted-foreground transition-colors",
              drag && "border-primary bg-primary/5",
            )}
          >
            <Upload className="size-6" />
            {upload.isPending ? "Uploading…" : "Drop files here or click to browse"}
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              multiple
              hidden
              onChange={(e) => e.target.files && upload.mutate(Array.from(e.target.files))}
            />
          </div>
          <div className="flex gap-2">
            <PasteDialog projectId={project.id} />
            <GenerateDialog project={project} docs={docs ?? []} onGenerated={onGenerated} />
          </div>
          {docs && docs.length === 0 && <EmptyState title="No documents" description="Upload or paste the client brief." />}
          <Accordion>
            {docs?.map((d) => (
              <AccordionItem key={d.id} value={d.id}>
                <AccordionTrigger>
                  <span className="flex items-center gap-2">
                    <FileText className="size-4" /> {d.filename}
                    <span className="text-xs text-muted-foreground">
                      {d.chunk_count} chunks · {d.chars.toLocaleString()} chars · {date(d.created_at)}
                    </span>
                  </span>
                </AccordionTrigger>
                <AccordionContent className="space-y-2">
                  <ChunkViewer doc={d} />
                  <Button variant="ghost" size="sm" onClick={() => remove.mutate(d.id)}>
                    <Trash2 /> Remove
                  </Button>
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Project</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div>
            <span className="text-muted-foreground">Domain: </span>
            {project.domain || "—"}
          </div>
          <div>
            <span className="text-muted-foreground">Created: </span>
            {date(project.created_at)}
          </div>
          {project.delivered_at && (
            <div>
              <span className="text-muted-foreground">Delivered: </span>
              {date(project.delivered_at)}
            </div>
          )}
          <p className="text-muted-foreground">{project.description}</p>
        </CardContent>
      </Card>
    </div>
  );
}
