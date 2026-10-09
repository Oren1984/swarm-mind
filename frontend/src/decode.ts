// Decoding and display formatting helpers (pure functions, unit tested).

export function base64ToBytes(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

/** Inverse of numpy.packbits (most significant bit first). */
export function unpackBits(bytes: Uint8Array, count: number): Uint8Array {
  const bits = new Uint8Array(count);
  for (let i = 0; i < count; i++) bits[i] = (bytes[i >> 3] >> (7 - (i & 7))) & 1;
  return bits;
}

/** Undefined measurements are shown as an em dash, never as 0. */
export function fmt(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toFixed(digits);
}

export function fmtSigned(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return (value > 0 ? "+" : "") + value.toFixed(digits);
}

export function fmtPct(fraction: number | null | undefined, digits = 0): string {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return "—";
  return (fraction * 100).toFixed(digits) + "%";
}

/** "Nice" axis ceiling: 1, 2 or 5 times a power of ten, at least 10. */
export function niceCeil(value: number): number {
  if (value <= 10) return 10;
  const pow = Math.pow(10, Math.floor(Math.log10(value)));
  for (const m of [1, 2, 5, 10]) if (value <= m * pow) return m * pow;
  return 10 * pow;
}
