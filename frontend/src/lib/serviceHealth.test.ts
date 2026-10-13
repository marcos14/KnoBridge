import { describe, expect, it } from "vitest";

import { serviceDetailKey } from "./serviceHealth";

describe("serviceDetailKey", () => {
  it("test_service_detail_key_maps_known_details", () => {
    expect(serviceDetailKey("database unreachable")).toBe("databaseUnreachable");
    expect(serviceDetailKey("no worker polling the task queue")).toBe("noWorkerPolling");
    expect(serviceDetailKey("temporal down")).toBe("temporalDown");
  });

  it("test_service_detail_key_is_undefined_for_null_or_unknown", () => {
    expect(serviceDetailKey(null)).toBeUndefined();
    expect(serviceDetailKey("something new")).toBeUndefined();
    expect(serviceDetailKey("toString")).toBeUndefined();
  });
});
