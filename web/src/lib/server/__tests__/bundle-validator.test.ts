// @vitest-environment node
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalize } from "json-canonicalize";
import { describe, expect, it } from "vitest";

import type { WebReportBundleV1 } from "../../../../../contracts/web-report/v1/generated/types";
import {
  MAX_REPORT_IMPORT_BYTES,
  validateBundleBytes,
} from "@/lib/server/bundle-validator";

const fixtureRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../contracts/web-report/v1/fixtures",
);

describe("bundle validator", () => {
  it("accepts the frozen valid bundle fixture", async () => {
    const bundle = await validateBundleBytes(
      await readFile(path.join(fixtureRoot, "valid-poc.json")),
    );
    expect(bundle.bundle_version).toBe("1.0.0");
  });

  it.each([
    ["invalid-hash.json", "bundle hash"],
    ["invalid-reference.json", "Evidence Link"],
  ])("rejects %s with its semantic violation", async (name, expected) => {
    await expect(
      validateBundleBytes(await readFile(path.join(fixtureRoot, name))),
    ).rejects.toThrow(expected);
  });

  it("rejects oversized bytes before parsing JSON", async () => {
    await expect(
      validateBundleBytes(new Uint8Array(MAX_REPORT_IMPORT_BYTES + 1)),
    ).rejects.toThrow("52,428,800");
  });

  it.each([
    "/etc/passwd",
    "/var/lib/trusted-ceo/report.json",
    "/tmp/trusted-ceo/source.csv",
  ])("rejects POSIX absolute display locator %s", async (displayLocator) => {
    const bundle = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    bundle.source_view[0].locator_summaries[0].display_locator = displayLocator;
    const hashBody = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete hashBody.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(hashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(new TextEncoder().encode(JSON.stringify(bundle))),
    ).rejects.toThrow("absolute path");
  });

  it("allows an RFC 6901 JSON Pointer display locator", async () => {
    const bundle = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    bundle.source_view[0].locator_summaries[0].locator_type = "json_pointer";
    bundle.source_view[0].locator_summaries[0].display_locator = "/records/0";
    const hashBody = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete hashBody.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(hashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(new TextEncoder().encode(JSON.stringify(bundle))),
    ).resolves.toMatchObject({ bundle_hash: bundle.bundle_hash });
  });

  it("requires the issue graph to exactly project Final Result values", async () => {
    const nodeMismatch = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    nodeMismatch.presentation_manifest.issue_graph.nodes[0].label_ko =
      "tampered label";
    const nodeHashBody =
      structuredClone(nodeMismatch) as Partial<WebReportBundleV1>;
    delete nodeHashBody.bundle_hash;
    nodeMismatch.bundle_hash = createHash("sha256")
      .update(canonicalize(nodeHashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(
        new TextEncoder().encode(JSON.stringify(nodeMismatch)),
      ),
    ).rejects.toThrow("issue graph node differs");

    const edgeMismatch = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    const peer = structuredClone(edgeMismatch.final_result.issues[0]);
    peer.issue_id = "issue_peer";
    edgeMismatch.final_result.issues.push(peer);
    edgeMismatch.presentation_manifest.issue_graph.nodes.push({
      issue_ref: peer.issue_id,
      label_ko: peer.title_template,
      grade: peer.primary_grade,
    });
    edgeMismatch.final_result.cross_issue_relations.push({
      relation_id: "relation_main",
      from_issue_ref: "issue_main",
      to_issue_ref: "issue_peer",
      relation_type: "supports",
    });
    edgeMismatch.presentation_manifest.issue_graph.edges.push({
      relation_id: "relation_main",
      from_issue_ref: "issue_main",
      to_issue_ref: "issue_peer",
      relation_type: "contradicts",
    });
    const edgeHashBody =
      structuredClone(edgeMismatch) as Partial<WebReportBundleV1>;
    delete edgeHashBody.bundle_hash;
    edgeMismatch.bundle_hash = createHash("sha256")
      .update(canonicalize(edgeHashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(
        new TextEncoder().encode(JSON.stringify(edgeMismatch)),
      ),
    ).rejects.toThrow("issue graph edge differs");
  });

  it("rejects issue graph nodes that are not sorted by issue_ref", async () => {
    const bundle = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    const peer = structuredClone(bundle.final_result.issues[0]);
    peer.issue_id = "issue_peer";
    bundle.final_result.issues.push(peer);
    bundle.presentation_manifest.issue_graph.nodes.push({
      issue_ref: peer.issue_id,
      label_ko: peer.title_template,
      grade: peer.primary_grade,
    });
    bundle.presentation_manifest.issue_graph.nodes.reverse();
    const hashBody = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete hashBody.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(hashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(new TextEncoder().encode(JSON.stringify(bundle))),
    ).rejects.toThrow("issue graph node IDs must be sorted");
  });

  it("rejects issue graph edges that are not sorted by relation_id", async () => {
    const bundle = JSON.parse(
      await readFile(path.join(fixtureRoot, "valid-poc.json"), "utf8"),
    ) as WebReportBundleV1;
    const peer = structuredClone(bundle.final_result.issues[0]);
    peer.issue_id = "issue_peer";
    bundle.final_result.issues.push(peer);
    bundle.presentation_manifest.issue_graph.nodes.push({
      issue_ref: peer.issue_id,
      label_ko: peer.title_template,
      grade: peer.primary_grade,
    });
    const firstRelation = {
      relation_id: "relation_a",
      from_issue_ref: "issue_main",
      to_issue_ref: "issue_peer",
      relation_type: "supports" as const,
    };
    const secondRelation = {
      relation_id: "relation_b",
      from_issue_ref: "issue_peer",
      to_issue_ref: "issue_main",
      relation_type: "contradicts" as const,
    };
    bundle.final_result.cross_issue_relations.push(
      firstRelation,
      secondRelation,
    );
    bundle.presentation_manifest.issue_graph.edges.push(
      secondRelation,
      firstRelation,
    );
    const hashBody = structuredClone(bundle) as Partial<WebReportBundleV1>;
    delete hashBody.bundle_hash;
    bundle.bundle_hash = createHash("sha256")
      .update(canonicalize(hashBody), "utf8")
      .digest("hex");

    await expect(
      validateBundleBytes(new TextEncoder().encode(JSON.stringify(bundle))),
    ).rejects.toThrow("issue graph edge IDs must be sorted");
  });
});
