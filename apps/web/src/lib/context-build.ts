export type ContextBuildPreviewMode =
  | "single_file_preview"
  | "loose_batch_preview"
  | "source_pack_candidate_preview"
  | "invalid_preview";

export type ContextBuildPreviewFile = {
  name: string;
  size: number;
  relativePath?: string;
  type?: string;
  lastModified?: number;
};

export type ContextBuildPreview = {
  mode: ContextBuildPreviewMode;
  fileCount: number;
  supportedFileCount: number;
  blockedFiles: string[];
  hasSourceManifest: boolean;
  extensionCounts: Record<string, number>;
};

const SOURCE_MANIFEST_NAME = "00_source_manifest.md";
const SUPPORTED_EXTENSIONS = new Set(["csv", "docx", "md", "pdf", "txt", "xlsx", "zip"]);
const BLOCKED_EXTENSIONS = new Set([
  "bat",
  "cmd",
  "com",
  "dll",
  "env",
  "exe",
  "key",
  "js",
  "msi",
  "pem",
  "ps1",
  "scr",
  "sh"
]);

export function detectContextBuildPreview(
  files: readonly ContextBuildPreviewFile[]
): ContextBuildPreview {
  const extensionCounts: Record<string, number> = {};
  const supportedFiles: ContextBuildPreviewFile[] = [];
  const blockedFiles: string[] = [];
  let hasSourceManifest = false;

  for (const file of files) {
    const extension = extensionFor(file.name);
    if (extension) {
      extensionCounts[extension] = (extensionCounts[extension] ?? 0) + 1;
    }

    if (normalizedBasename(file) === SOURCE_MANIFEST_NAME) {
      hasSourceManifest = true;
    }

    if (BLOCKED_EXTENSIONS.has(extension)) {
      blockedFiles.push(file.name);
      continue;
    }

    if (SUPPORTED_EXTENSIONS.has(extension)) {
      supportedFiles.push(file);
    }
  }

  return {
    mode: previewMode({
      blockedCount: blockedFiles.length,
      fileCount: files.length,
      hasSourceManifest,
      hasZip: (extensionCounts.zip ?? 0) > 0,
      supportedCount: supportedFiles.length
    }),
    fileCount: files.length,
    supportedFileCount: supportedFiles.length,
    blockedFiles,
    hasSourceManifest,
    extensionCounts
  };
}

function previewMode(input: {
  blockedCount: number;
  fileCount: number;
  hasSourceManifest: boolean;
  hasZip: boolean;
  supportedCount: number;
}): ContextBuildPreviewMode {
  if (input.fileCount === 0 || input.blockedCount > 0 || input.supportedCount === 0) {
    return "invalid_preview";
  }
  if (input.hasSourceManifest || (input.hasZip && input.fileCount === 1)) {
    return "source_pack_candidate_preview";
  }
  if (input.supportedCount === 1) {
    return "single_file_preview";
  }
  return "loose_batch_preview";
}

function extensionFor(name: string): string {
  const basename = normalizedBasename({ name });
  const lastDot = basename.lastIndexOf(".");
  if (lastDot < 0 || lastDot === basename.length - 1) {
    return "";
  }
  return basename.slice(lastDot + 1);
}

function normalizedBasename(file: Pick<ContextBuildPreviewFile, "name" | "relativePath">): string {
  const candidate = file.relativePath || file.name;
  return candidate.replaceAll("\\", "/").split("/").pop()?.trim().toLowerCase() ?? "";
}
