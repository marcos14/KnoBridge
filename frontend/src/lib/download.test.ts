import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { stubDownloads } from "@/test/downloads";

import { attachmentFilename, saveBlob } from "./download";

describe("attachmentFilename", () => {
  it("test_attachment_filename_prefers_the_utf8_name", () => {
    expect(
      attachmentFilename(
        `attachment; filename="erp_local-faturamento.zip"; filename*=UTF-8''erp%20local-fatura%C3%A7%C3%A3o.zip`,
      ),
    ).toBe("erp local-faturação.zip");
  });

  it("test_attachment_filename_reads_the_plain_name", () => {
    expect(attachmentFilename('attachment; filename="erp-local.zip"')).toBe("erp-local.zip");
    expect(attachmentFilename("attachment; filename=erp-local.zip")).toBe("erp-local.zip");
  });

  it("test_attachment_filename_falls_back_when_the_utf8_name_is_malformed", () => {
    expect(
      attachmentFilename(`attachment; filename="plano.zip"; filename*=UTF-8''%E0%A4%A.zip`),
    ).toBe("plano.zip");
  });

  it("test_attachment_filename_falls_back_when_the_utf8_name_is_unusable", () => {
    expect(attachmentFilename(`attachment; filename="plano.zip"; filename*=UTF-8''..`)).toBe(
      "plano.zip",
    );
  });

  it("test_attachment_filename_drops_directories_and_unsafe_characters", () => {
    expect(attachmentFilename(`attachment; filename*=UTF-8''..%2F..%2Fetc%2Fa%3Fb.zip`)).toBe(
      "a_b.zip",
    );
    expect(attachmentFilename('attachment; filename="C:\\temp\\x.zip"')).toBe("x.zip");
  });

  it("test_attachment_filename_is_null_without_a_name", () => {
    expect(attachmentFilename(null)).toBeNull();
    expect(attachmentFilename("attachment")).toBeNull();
    expect(attachmentFilename('attachment; filename=""')).toBeNull();
  });
});

describe("saveBlob", () => {
  let downloads: ReturnType<typeof stubDownloads>;

  beforeEach(() => {
    downloads = stubDownloads();
  });

  afterEach(() => {
    downloads.restore();
  });

  it("test_save_blob_clicks_a_download_link_and_releases_the_url", () => {
    const blob = new Blob(["zip"]);

    saveBlob(blob, "erp-local.zip");

    expect(downloads.blobs).toEqual([blob]);
    expect(downloads.saved).toEqual([{ name: "erp-local.zip", href: "blob:download-1" }]);
    expect(downloads.revoked).toEqual(["blob:download-1"]);
  });
});
