/* Minimal, zero-dependency QR Code (Model 2, Byte mode, ECC-L) SVG generator */
(function (global) {
  "use strict";

  // Capacity & EC table for ECC-L, versions 1..14
  // [version, totalCodewords, ecPerBlock, numBlocksG1, dataPerBlockG1, numBlocksG2, dataPerBlockG2, alignCoords]
  const VERSIONS = [
    null,
    [1, 26, 7, 1, 19, 0, 0, []],
    [2, 44, 10, 1, 34, 0, 0, [6, 18]],
    [3, 70, 15, 1, 55, 0, 0, [6, 22]],
    [4, 100, 20, 1, 80, 0, 0, [6, 26]],
    [5, 134, 26, 1, 108, 0, 0, [6, 30]],
    [6, 172, 18, 2, 68, 0, 0, [6, 34]],
    [7, 196, 20, 2, 78, 0, 0, [6, 22, 38]],
    [8, 242, 24, 2, 97, 0, 0, [6, 24, 42]],
    [9, 292, 30, 2, 116, 0, 0, [6, 26, 46]],
    [10, 346, 18, 2, 68, 2, 69, [6, 28, 50]],
    [11, 404, 20, 4, 81, 0, 0, [6, 30, 54]],
    [12, 466, 24, 2, 92, 2, 93, [6, 32, 58]],
    [13, 532, 26, 4, 107, 0, 0, [6, 34, 62]],
    [14, 581, 30, 3, 115, 1, 116, [6, 26, 46, 66]],
  ];

  // GF(256) exp/log tables (poly 0x11d)
  const EXP = new Uint8Array(512);
  const LOG = new Uint8Array(256);
  (function initGF() {
    let x = 1;
    for (let i = 0; i < 255; i++) {
      EXP[i] = x;
      LOG[x] = i;
      x <<= 1;
      if (x & 0x100) x ^= 0x11d;
    }
    for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  })();

  function gfMul(a, b) {
    if (a === 0 || b === 0) return 0;
    return EXP[LOG[a] + LOG[b]];
  }

  function rsGenerator(degree) {
    let poly = [1];
    for (let i = 0; i < degree; i++) {
      const next = new Array(poly.length + 1).fill(0);
      const factor = EXP[i];
      for (let j = 0; j < poly.length; j++) {
        next[j] ^= poly[j];
        next[j + 1] ^= gfMul(poly[j], factor);
      }
      poly = next;
    }
    return poly;
  }

  function rsEncode(data, ecCount) {
    const gen = rsGenerator(ecCount);
    const res = new Uint8Array(data.length + ecCount);
    res.set(data);
    for (let i = 0; i < data.length; i++) {
      const coef = res[i];
      if (coef !== 0) {
        for (let j = 0; j < gen.length; j++) {
          res[i + j] ^= gfMul(gen[j], coef);
        }
      }
    }
    return res.slice(data.length);
  }

  function encodeQR(text) {
    const bytes = new TextEncoder().encode(text);
    let ver = null;
    for (let v = 1; v < VERSIONS.length; v++) {
      const info = VERSIONS[v];
      const dataCap = info[3] * info[4] + info[5] * info[6];
      const ccBits = v >= 10 ? 16 : 8;
      const neededBits = 4 + ccBits + bytes.length * 8;
      if (neededBits <= dataCap * 8) {
        ver = info;
        break;
      }
    }
    if (!ver) throw new Error("Data too long for QR");

    const [vNum, , ecPerBlock, g1Count, g1Len, g2Count, g2Len, alignCoords] = ver;
    const dataCap = g1Count * g1Len + g2Count * g2Len;
    const bits = [];
    const pushBits = (val, len) => {
      for (let i = len - 1; i >= 0; i--) bits.push((val >> i) & 1);
    };

    pushBits(0b0100, 4); // Byte mode
    pushBits(bytes.length, vNum >= 10 ? 16 : 8);
    for (const b of bytes) pushBits(b, 8);
    const termLen = Math.min(4, dataCap * 8 - bits.length);
    pushBits(0, termLen);
    while (bits.length % 8 !== 0) bits.push(0);

    const dataBytes = [];
    for (let i = 0; i < bits.length; i += 8) {
      let byte = 0;
      for (let j = 0; j < 8; j++) byte = (byte << 1) | bits[i + j];
      dataBytes.push(byte);
    }
    const pads = [0xec, 0x11];
    let padIdx = 0;
    while (dataBytes.length < dataCap) {
      dataBytes.push(pads[padIdx % 2]);
      padIdx++;
    }

    // Split into blocks & compute EC
    const dataBlocks = [];
    const ecBlocks = [];
    let offset = 0;
    for (let i = 0; i < g1Count; i++) {
      const blk = dataBytes.slice(offset, offset + g1Len);
      offset += g1Len;
      dataBlocks.push(blk);
      ecBlocks.push(rsEncode(blk, ecPerBlock));
    }
    for (let i = 0; i < g2Count; i++) {
      const blk = dataBytes.slice(offset, offset + g2Len);
      offset += g2Len;
      dataBlocks.push(blk);
      ecBlocks.push(rsEncode(blk, ecPerBlock));
    }

    const interleaved = [];
    const maxDataLen = Math.max(g1Len, g2Len);
    for (let i = 0; i < maxDataLen; i++) {
      for (const blk of dataBlocks) {
        if (i < blk.length) interleaved.push(blk[i]);
      }
    }
    for (let i = 0; i < ecPerBlock; i++) {
      for (const blk of ecBlocks) {
        interleaved.push(blk[i]);
      }
    }

    const size = vNum * 4 + 17;
    const grid = Array.from({ length: size }, () => new Int8Array(size).fill(-1));
    const reserved = Array.from({ length: size }, () => new Uint8Array(size));

    const setMod = (r, c, val, isRes = true) => {
      if (r >= 0 && r < size && c >= 0 && c < size) {
        grid[r][c] = val;
        if (isRes) reserved[r][c] = 1;
      }
    };

    const drawFinder = (r0, c0) => {
      for (let r = -1; r <= 7; r++) {
        for (let c = -1; c <= 7; c++) {
          const rr = r0 + r;
          const cc = c0 + c;
          if (rr < 0 || rr >= size || cc < 0 || cc >= size) continue;
          const inOuter = r >= 0 && r <= 6 && c >= 0 && c <= 6;
          const onBorder = r === 0 || r === 6 || c === 0 || c === 6;
          const inInner = r >= 2 && r <= 4 && c >= 2 && c <= 4;
          setMod(rr, cc, inOuter && (onBorder || inInner) ? 1 : 0, true);
        }
      }
    };

    drawFinder(0, 0);
    drawFinder(0, size - 7);
    drawFinder(size - 7, 0);

    // Timing patterns
    for (let i = 8; i < size - 8; i++) {
      setMod(6, i, i % 2 === 0 ? 1 : 0, true);
      setMod(i, 6, i % 2 === 0 ? 1 : 0, true);
    }

    // Alignment patterns
    for (const r of alignCoords) {
      for (const c of alignCoords) {
        if (reserved[r][c]) continue;
        for (let dr = -2; dr <= 2; dr++) {
          for (let dc = -2; dc <= 2; dc++) {
            const onEdge = Math.abs(dr) === 2 || Math.abs(dc) === 2 || (dr === 0 && dc === 0);
            setMod(r + dr, c + dc, onEdge ? 1 : 0, true);
          }
        }
      }
    }

    // Dark module + reserve format info
    setMod(size - 8, 8, 1, true);
    for (let i = 0; i < 9; i++) {
      if (i !== 6) {
        reserved[8][i] = 1;
        reserved[i][8] = 1;
      }
    }
    for (let i = 0; i < 8; i++) {
      reserved[8][size - 1 - i] = 1;
      reserved[size - 1 - i][8] = 1;
    }

    // Version info for v >= 7
    if (vNum >= 7) {
      let rem = vNum;
      for (let i = 0; i < 12; i++) {
        rem = (rem << 1) ^ ((rem >> 11) * 0x1f25);
      }
      const verBits = (vNum << 12) | rem;
      for (let i = 0; i < 18; i++) {
        const bit = (verBits >> i) & 1;
        const a = Math.floor(i / 3);
        const b = size - 11 + (i % 3);
        setMod(a, b, bit, true);
        setMod(b, a, bit, true);
      }
    }

    // Place data bits (mask 0: (r + c) % 2 === 0)
    const msgBits = [];
    for (const byte of interleaved) {
      for (let i = 7; i >= 0; i--) msgBits.push((byte >> i) & 1);
    }

    let bitIdx = 0;
    let up = true;
    for (let col = size - 1; col > 0; col -= 2) {
      if (col === 6) col--;
      for (let step = 0; step < size; step++) {
        const r = up ? size - 1 - step : step;
        for (let dc = 0; dc < 2; dc++) {
          const c = col - dc;
          if (!reserved[r][c]) {
            const b = bitIdx < msgBits.length ? msgBits[bitIdx++] : 0;
            const masked = (r + c) % 2 === 0 ? b ^ 1 : b;
            grid[r][c] = masked;
          }
        }
      }
      up = !up;
    }

    // Format info for ECC-L (01) + Mask 0 (000) -> 0b01000 = 8
    // Precomputed BCH(15,5) masked with 0x5412 for L+0: 0x77c4
    const fmt = 0x77c4;
    for (let i = 0; i < 15; i++) {
      const bit = (fmt >> i) & 1;
      // Top-left horizontal & vertical
      if (i < 6) grid[8][i] = bit;
      else if (i < 8) grid[8][i + 1] = bit;
      else grid[14 - i][8] = bit;

      if (i < 8) grid[size - 1 - i][8] = bit;
      else grid[8][size - 15 + i] = bit;
    }

    return { size, grid };
  }

  function toSVG(text, pxSize = 220) {
    const { size, grid } = encodeQR(text);
    const margin = 3;
    const total = size + margin * 2;
    let paths = "";
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        if (grid[r][c] === 1) {
          paths += `M${c + margin},${r + margin}h1v1h-1z`;
        }
      }
    }
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${total} ${total}" width="${pxSize}" height="${pxSize}" shape-rendering="crispEdges"><rect width="${total}" height="${total}" fill="#ffffff"/><path d="${paths}" fill="#0f172a"/></svg>`;
  }

  global.XrayQR = { toSVG };
})(window);
