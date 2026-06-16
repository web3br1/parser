import type { ReadPathVerdict } from "../types";

export interface GoldenCase {
  id: string;
  query: string;
  expectedChunkIds: string[];
  expectedCitationQuotes: string[];
  expectedVerdict: ReadPathVerdict;
}

export const starterGoldenSet: GoldenCase[] = [
  {
    id: "capa-approval",
    query: "Quem aprova CAPA crítica?",
    expectedChunkIds: ["chunk_capa_approval"],
    expectedCitationQuotes: ["Gerente da Qualidade deve aprovar CAPA crítica"],
    expectedVerdict: "sufficient",
  },
  {
    id: "unknown-policy",
    query: "Qual a regra para benefício não documentado?",
    expectedChunkIds: [],
    expectedCitationQuotes: [],
    expectedVerdict: "abstain_required",
  },
];
