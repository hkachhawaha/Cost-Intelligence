import { describe, expect, it } from "vitest";
import { ApiError } from "./api";

describe("ApiError", () => {
  it("carries status, detail, and requestId", () => {
    const err = new ApiError(403, "missing permission: contract:write", "req-123");
    expect(err.status).toBe(403);
    expect(err.detail).toBe("missing permission: contract:write");
    expect(err.requestId).toBe("req-123");
    expect(err).toBeInstanceOf(Error);
  });
});
