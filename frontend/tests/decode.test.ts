import { describe, expect, it } from "vitest";
import { base64ToBytes, fmt, fmtPct, fmtSigned, niceCeil, unpackBits } from "../src/decode";

describe("decoding backend payloads", () => {
  it("decodes base64 into bytes", () => {
    expect(Array.from(base64ToBytes("AAECAw=="))).toEqual([0, 1, 2, 3]);
    expect(Array.from(base64ToBytes("/w=="))).toEqual([255]);
  });

  it("unpacks bits like numpy.packbits (most significant bit first)", () => {
    // numpy.packbits([1,0,1,0,0,0,0,0, 1,1]) -> [160, 192]
    expect(Array.from(unpackBits(new Uint8Array([160, 192]), 10))).toEqual([1, 0, 1, 0, 0, 0, 0, 0, 1, 1]);
  });
});

describe("formatting", () => {
  it("shows undefined measurements as a dash, never as zero", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(undefined)).toBe("—");
    expect(fmtPct(null)).toBe("—");
    expect(fmtSigned(null)).toBe("—");
    expect(fmt(0)).toBe("0");
  });

  it("formats numbers, signs and percentages", () => {
    expect(fmt(12.345, 1)).toBe("12.3");
    expect(fmtSigned(4)).toBe("+4");
    expect(fmtSigned(-4.25, 1)).toBe("-4.3");
    expect(fmtPct(0.4567)).toBe("46%");
  });

  it("rounds axis maxima up to 1/2/5 steps", () => {
    expect(niceCeil(0)).toBe(10);
    expect(niceCeil(11)).toBe(20);
    expect(niceCeil(775)).toBe(1000);
    expect(niceCeil(1712)).toBe(2000);
    expect(niceCeil(2001)).toBe(5000);
  });
});
