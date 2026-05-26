import {
  detectContextBuildPreview,
  type ContextBuildPreviewFile
} from "./context-build";

function file(name: string, size = 1024, relativePath?: string): ContextBuildPreviewFile {
  return {
    name,
    size,
    relativePath,
    type: "text/plain",
    lastModified: 1
  };
}

function expectMode(
  files: ContextBuildPreviewFile[],
  expectedMode: ReturnType<typeof detectContextBuildPreview>["mode"]
): ReturnType<typeof detectContextBuildPreview> {
  const result = detectContextBuildPreview(files);
  if (result.mode !== expectedMode) {
    throw new Error(`Expected ${expectedMode}, got ${result.mode}.`);
  }
  return result;
}

expectMode([], "invalid_preview");

const single = expectMode([file("policy.md")], "single_file_preview");
if (single.supportedFileCount !== 1 || single.extensionCounts.md !== 1) {
  throw new Error("Single supported file should be counted as one markdown file.");
}

const spreadsheet = expectMode([file("prices.xlsx")], "single_file_preview");
if (spreadsheet.supportedFileCount !== 1 || spreadsheet.extensionCounts.xlsx !== 1) {
  throw new Error("XLSX files should be supported by the optimistic preview.");
}

const zipSourcePack = expectMode([file("source-pack.zip", 2048)], "source_pack_candidate_preview");
if (zipSourcePack.supportedFileCount !== 1 || zipSourcePack.extensionCounts.zip !== 1) {
  throw new Error("ZIP source packs should be supported by the optimistic preview.");
}

const batch = expectMode(
  [file("policy.md"), file("pricing.csv"), file("faq.txt")],
  "loose_batch_preview"
);
if (
  batch.supportedFileCount !== 3 ||
  batch.extensionCounts.md !== 1 ||
  batch.extensionCounts.csv !== 1 ||
  batch.extensionCounts.txt !== 1
) {
  throw new Error("Loose batch should report counts by extension.");
}

const sourcePack = expectMode(
  [
    file("00_source_manifest.md", 1000, "compounding/00_source_manifest.md"),
    file("01_reference.md", 1000, "compounding/01_reference.md")
  ],
  "source_pack_candidate_preview"
);
if (!sourcePack.hasSourceManifest) {
  throw new Error("Source pack candidate should report manifest presence.");
}

const blocked = expectMode([file("payload.exe")], "invalid_preview");
if (!blocked.blockedFiles.includes("payload.exe")) {
  throw new Error("Blocked extensions should be reported by file name.");
}

const sensitive = expectMode(
  [file(".env"), file("private.pem"), file("signing.key")],
  "invalid_preview"
);
if (
  !sensitive.blockedFiles.includes(".env") ||
  !sensitive.blockedFiles.includes("private.pem") ||
  !sensitive.blockedFiles.includes("signing.key")
) {
  throw new Error("Sensitive local config and key files should be reported as blocked.");
}

const mixed = expectMode([file("policy.md"), file("payload.exe")], "invalid_preview");
if (mixed.supportedFileCount !== 1 || mixed.blockedFiles.length !== 1) {
  throw new Error("Invalid mixed selections should still expose supported and blocked counts.");
}
