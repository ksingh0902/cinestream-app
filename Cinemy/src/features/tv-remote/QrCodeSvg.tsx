import React, { useMemo } from 'react';

/**
 * Self-contained, zero-dependency QR Code SVG encoder (ISO/IEC 18004, Byte mode, ECC Level L).
 * Supports versions 1..6 (up to 134 bytes) — ideal for short-lived CINEMY pairing URLs.
 */

const GF_EXP = new Uint8Array(512);
const GF_LOG = new Uint8Array(256);
(() => {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    GF_EXP[i] = x;
    GF_LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) {
    GF_EXP[i] = GF_EXP[i - 255];
  }
})();

function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return GF_EXP[GF_LOG[a] + GF_LOG[b]];
}

function rsGeneratorPoly(degree: number): Uint8Array {
  let poly = new Uint8Array([1]);
  for (let i = 0; i < degree; i++) {
    const next = new Uint8Array(poly.length + 1);
    const factor = GF_EXP[i];
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= gfMul(poly[j], factor);
    }
    poly = next;
  }
  return poly;
}

function rsRemainder(data: Uint8Array, ecCount: number): Uint8Array {
  const gen = rsGeneratorPoly(ecCount);
  const rem = new Uint8Array(ecCount);
  for (let i = 0; i < data.length; i++) {
    const factor = data[i] ^ rem[0];
    for (let j = 0; j < ecCount - 1; j++) {
      rem[j] = rem[j + 1] ^ gfMul(gen[j + 1], factor);
    }
    rem[ecCount - 1] = gfMul(gen[ecCount], factor);
  }
  return rem;
}

interface QrVersionSpec {
  version: number;
  size: number;
  dataCodewords: number;
  ecCodewordsPerBlock: number;
  blocks: number;
  alignCenters: number[];
}

// ECC Level L specifications for versions 1..6
const VERSION_SPECS: QrVersionSpec[] = [
  { version: 1, size: 21, dataCodewords: 19, ecCodewordsPerBlock: 7, blocks: 1, alignCenters: [] },
  { version: 2, size: 25, dataCodewords: 34, ecCodewordsPerBlock: 10, blocks: 1, alignCenters: [6, 18] },
  { version: 3, size: 29, dataCodewords: 55, ecCodewordsPerBlock: 15, blocks: 1, alignCenters: [6, 22] },
  { version: 4, size: 33, dataCodewords: 80, ecCodewordsPerBlock: 20, blocks: 1, alignCenters: [6, 26] },
  { version: 5, size: 37, dataCodewords: 108, ecCodewordsPerBlock: 26, blocks: 1, alignCenters: [6, 30] },
  { version: 6, size: 41, dataCodewords: 136, ecCodewordsPerBlock: 18, blocks: 2, alignCenters: [6, 34] },
];

export function encodeQrMatrix(text: string): boolean[][] {
  const bytes = new TextEncoder().encode(text);
  // Byte mode header: 4 bits mode (0100) + 8 bits length = 12 bits -> 2 bytes overhead
  const spec =
    VERSION_SPECS.find((s) => bytes.length + 2 <= s.dataCodewords) ||
    VERSION_SPECS[VERSION_SPECS.length - 1];

  const bitBuf: number[] = [];
  const pushBits = (val: number, len: number) => {
    for (let i = len - 1; i >= 0; i--) bitBuf.push((val >>> i) & 1);
  };

  pushBits(0b0100, 4); // Byte mode
  const maxBytes = spec.dataCodewords - 2;
  const payload = bytes.slice(0, maxBytes);
  pushBits(payload.length, 8);
  for (let i = 0; i < payload.length; i++) pushBits(payload[i], 8);

  const totalDataBits = spec.dataCodewords * 8;
  const terminator = Math.min(4, totalDataBits - bitBuf.length);
  pushBits(0, terminator);
  while (bitBuf.length % 8 !== 0) bitBuf.push(0);

  const dataCw = new Uint8Array(spec.dataCodewords);
  for (let i = 0; i < bitBuf.length / 8; i++) {
    let b = 0;
    for (let j = 0; j < 8; j++) b = (b << 1) | bitBuf[i * 8 + j];
    dataCw[i] = b;
  }
  const padBytes = [0xec, 0x11];
  for (let i = bitBuf.length / 8, p = 0; i < spec.dataCodewords; i++, p++) {
    dataCw[i] = padBytes[p % 2];
  }

  // Split into blocks & interleave (supports 1 or 2 equal blocks for v1..v6 Level L)
  const blockSize = Math.floor(spec.dataCodewords / spec.blocks);
  const dataBlocks: Uint8Array[] = [];
  const ecBlocks: Uint8Array[] = [];
  for (let b = 0; b < spec.blocks; b++) {
    const slice = dataCw.slice(b * blockSize, (b + 1) * blockSize);
    dataBlocks.push(slice);
    ecBlocks.push(rsRemainder(slice, spec.ecCodewordsPerBlock));
  }

  const finalCodewords: number[] = [];
  for (let i = 0; i < blockSize; i++) {
    for (let b = 0; b < spec.blocks; b++) finalCodewords.push(dataBlocks[b][i]);
  }
  for (let i = 0; i < spec.ecCodewordsPerBlock; i++) {
    for (let b = 0; b < spec.blocks; b++) finalCodewords.push(ecBlocks[b][i]);
  }

  const size = spec.size;
  const modules: boolean[][] = Array.from({ length: size }, () => Array(size).fill(false));
  const isFunc: boolean[][] = Array.from({ length: size }, () => Array(size).fill(false));

  const setFunc = (r: number, c: number, dark: boolean) => {
    if (r >= 0 && r < size && c >= 0 && c < size) {
      modules[r][c] = dark;
      isFunc[r][c] = true;
    }
  };

  // Finder patterns + separators
  const drawFinder = (top: number, left: number) => {
    for (let dr = -1; dr <= 7; dr++) {
      for (let dc = -1; dc <= 7; dc++) {
        const r = top + dr;
        const c = left + dc;
        if (r < 0 || r >= size || c < 0 || c >= size) continue;
        const inOuter = dr >= 0 && dr <= 6 && dc >= 0 && dc <= 6;
        const dark =
          inOuter &&
          (dr === 0 || dr === 6 || dc === 0 || dc === 6 || (dr >= 2 && dr <= 4 && dc >= 2 && dc <= 4));
        setFunc(r, c, dark);
      }
    }
  };
  drawFinder(0, 0);
  drawFinder(0, size - 7);
  drawFinder(size - 7, 0);

  // Timing patterns
  for (let i = 8; i < size - 8; i++) {
    setFunc(6, i, i % 2 === 0);
    setFunc(i, 6, i % 2 === 0);
  }

  // Alignment patterns
  for (const r of spec.alignCenters) {
    for (const c of spec.alignCenters) {
      if (isFunc[r][c]) continue;
      for (let dr = -2; dr <= 2; dr++) {
        for (let dc = -2; dc <= 2; dc++) {
          const dist = Math.max(Math.abs(dr), Math.abs(dc));
          setFunc(r + dr, c + dc, dist !== 1);
        }
      }
    }
  }

  // Reserve format info areas + dark module
  for (let i = 0; i <= 8; i++) {
    if (i !== 6) {
      setFunc(8, i, false);
      setFunc(i, 8, false);
    }
  }
  for (let i = size - 8; i < size; i++) {
    setFunc(8, i, false);
    setFunc(i, 8, false);
  }
  setFunc(size - 8, 8, true);

  // Place data bits in zigzag columns
  const allBits: number[] = [];
  for (const cw of finalCodewords) {
    for (let i = 7; i >= 0; i--) allBits.push((cw >>> i) & 1);
  }
  let bitIdx = 0;
  let upward = true;
  for (let right = size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let step = 0; step < size; step++) {
      const r = upward ? size - 1 - step : step;
      for (let colOff = 0; colOff < 2; colOff++) {
        const c = right - colOff;
        if (!isFunc[r][c]) {
          const bit = bitIdx < allBits.length ? allBits[bitIdx++] : 0;
          // Apply mask pattern 0: (r + c) % 2 === 0
          const masked = ((r + c) % 2 === 0) ? bit ^ 1 : bit;
          modules[r][c] = masked === 1;
        }
      }
    }
    upward = !upward;
  }

  // Format information for ECC Level L (01) + Mask 0 (000) -> 15-bit BCH + XOR mask = 0x77C4
  const fmt = 0x77c4;
  for (let i = 0; i <= 5; i++) modules[8][i] = ((fmt >>> (14 - i)) & 1) === 1;
  modules[8][7] = ((fmt >>> 8) & 1) === 1;
  modules[8][8] = ((fmt >>> 7) & 1) === 1;
  modules[7][8] = ((fmt >>> 6) & 1) === 1;
  for (let i = 9; i < 15; i++) modules[14 - i][8] = ((fmt >>> (14 - i)) & 1) === 1;
  for (let i = 0; i < 8; i++) modules[8][size - 1 - i] = ((fmt >>> i) & 1) === 1;
  for (let i = 8; i < 15; i++) modules[size - 15 + i][8] = ((fmt >>> i) & 1) === 1;

  return modules;
}

interface QrCodeSvgProps {
  value: string;
  size?: number;
  label?: string;
}

export const QrCodeSvg: React.FC<QrCodeSvgProps> = ({ value, size = 200, label = 'TV Pairing QR Code' }) => {
  const matrix = useMemo(() => encodeQrMatrix(value), [value]);
  const quiet = 2;
  const dim = matrix.length + quiet * 2;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${dim} ${dim}`}
      role="img"
      aria-label={label}
      style={{
        display: 'block',
        background: '#ffffff',
        borderRadius: '12px',
        padding: '8px',
      }}
    >
      <rect width={dim} height={dim} fill="#ffffff" />
      {matrix.map((row, r) =>
        row.map((dark, c) =>
          dark ? (
            <rect
              key={`${r}-${c}`}
              x={c + quiet}
              y={r + quiet}
              width={1}
              height={1}
              fill="#0e0f13"
            />
          ) : null
        )
      )}
    </svg>
  );
};
