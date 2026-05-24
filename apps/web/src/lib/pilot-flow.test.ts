import {
  buildPilotSteps,
  summarizePilotReadiness,
  type PilotSnapshot
} from "./pilot-flow";

const emptySnapshot: PilotSnapshot = {
  apiReachable: true,
  sourceCount: 0,
  latestJobStatus: null,
  reviewPending: 0,
  unknownOpen: 0,
  knowledgeTotal: 0
};

const activeSnapshot: PilotSnapshot = {
  apiReachable: true,
  sourceCount: 2,
  latestJobStatus: "succeeded",
  reviewPending: 3,
  unknownOpen: 1,
  knowledgeTotal: 5
};

const blockedSnapshot: PilotSnapshot = {
  apiReachable: false,
  sourceCount: 0,
  latestJobStatus: null,
  reviewPending: 0,
  unknownOpen: 0,
  knowledgeTotal: 0
};

const emptySteps = buildPilotSteps(emptySnapshot);
if (emptySteps.map((step) => step.id).join(",") !== "runtime,upload,pipeline,review,query") {
  throw new Error("Pilot steps should remain in runtime-to-query order.");
}
if (emptySteps[0]?.status !== "ready" || emptySteps[1]?.status !== "next") {
  throw new Error("Empty but reachable pilot should ask the operator to upload first.");
}

const activeSteps = buildPilotSteps(activeSnapshot);
if (activeSteps[3]?.status !== "attention" || activeSteps[4]?.status !== "ready") {
  throw new Error("Active pilot should flag pending review while allowing query validation.");
}

const cancelledSteps = buildPilotSteps({
  ...activeSnapshot,
  latestJobStatus: "cancelled",
  reviewPending: 0,
  unknownOpen: 0
});
if (
  cancelledSteps[2]?.status !== "attention" ||
  cancelledSteps[3]?.detail !== "No open review or unknown items."
) {
  throw new Error("Cancelled ingest should require operator attention.");
}

const blockedSteps = buildPilotSteps(blockedSnapshot);
if (!blockedSteps.every((step) => step.status === "blocked")) {
  throw new Error("Unreachable API should block all pilot steps.");
}

if (summarizePilotReadiness(emptySnapshot).tone !== "warning") {
  throw new Error("Empty pilot should be a warning until a source is uploaded.");
}
if (summarizePilotReadiness(activeSnapshot).tone !== "success") {
  throw new Error("Active pilot with knowledge should be successful.");
}
if (summarizePilotReadiness(blockedSnapshot).tone !== "error") {
  throw new Error("Unreachable API should be an error.");
}
