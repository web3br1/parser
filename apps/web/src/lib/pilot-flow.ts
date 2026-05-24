export type PilotStepStatus = "ready" | "next" | "attention" | "blocked";

export type PilotSnapshot = {
  apiReachable: boolean;
  sourceCount: number;
  latestJobStatus: string | null;
  reviewPending: number;
  unknownOpen: number;
  knowledgeTotal: number;
};

export type PilotStep = {
  id: "runtime" | "upload" | "pipeline" | "review" | "query";
  label: string;
  status: PilotStepStatus;
  detail: string;
};

export type PilotReadiness = {
  tone: "success" | "warning" | "error";
  title: string;
  detail: string;
};

export function buildPilotSteps(snapshot: PilotSnapshot): PilotStep[] {
  if (!snapshot.apiReachable) {
    return pilotStepDefinitions().map((step) => ({
      ...step,
      status: "blocked",
      detail: "Local API is unavailable. Start the runtime before validating the pilot."
    }));
  }

  return [
    {
      id: "runtime",
      label: "Local runtime",
      status: "ready",
      detail: "API responded with the current token."
    },
    {
      id: "upload",
      label: "Source upload",
      status: snapshot.sourceCount > 0 ? "ready" : "next",
      detail:
        snapshot.sourceCount > 0
          ? `${snapshot.sourceCount} source(s) in this workspace.`
          : "Upload a file to start the flow."
    },
    {
      id: "pipeline",
      label: "Pipeline",
      status: pipelineStatus(snapshot.latestJobStatus),
      detail: snapshot.latestJobStatus
        ? `Latest job: ${snapshot.latestJobStatus.replaceAll("_", " ")}.`
        : "No ingest job found yet."
    },
    {
      id: "review",
      label: "Human review",
      status: snapshot.reviewPending || snapshot.unknownOpen ? "attention" : "ready",
      detail:
        snapshot.reviewPending || snapshot.unknownOpen
          ? `${snapshot.reviewPending} review item(s), ${snapshot.unknownOpen} open unknown item(s).`
          : "No open review or unknown items."
    },
    {
      id: "query",
      label: "Query",
      status: snapshot.knowledgeTotal > 0 ? "ready" : "next",
      detail:
        snapshot.knowledgeTotal > 0
          ? `${snapshot.knowledgeTotal} published record(s) available for query.`
          : "Publish knowledge to validate answers."
    }
  ];
}

export function summarizePilotReadiness(snapshot: PilotSnapshot): PilotReadiness {
  if (!snapshot.apiReachable) {
    return {
      tone: "error",
      title: "Local API unavailable",
      detail: "The front end is open, but it could not load data from the local runtime."
    };
  }
  if (snapshot.knowledgeTotal > 0) {
    return {
      tone: "success",
      title: "Pilot ready for query",
      detail: "This workspace already has published knowledge for validation questions."
    };
  }
  if (snapshot.sourceCount > 0) {
    return {
      tone: "warning",
      title: "Pilot in progress",
      detail: "Sources are loaded; follow pipeline, review, and publication."
    };
  }
  return {
    tone: "warning",
    title: "Pilot waiting for first source",
    detail: "Start by uploading a small document and follow the flow on this screen."
  };
}

function pipelineStatus(status: string | null): PilotStepStatus {
  if (!status) {
    return "next";
  }
  if (["cancelled", "failed", "error"].includes(status)) {
    return "attention";
  }
  if (["queued", "retrying", "running", "processing"].includes(status)) {
    return "attention";
  }
  if (["completed", "succeeded", "success"].includes(status)) {
    return "ready";
  }
  return "attention";
}

function pilotStepDefinitions(): Array<Pick<PilotStep, "id" | "label">> {
  return [
    { id: "runtime", label: "Local runtime" },
    { id: "upload", label: "Source upload" },
    { id: "pipeline", label: "Pipeline" },
    { id: "review", label: "Human review" },
    { id: "query", label: "Query" }
  ];
}
