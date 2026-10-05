const fs = require("fs");

const file = "src/App.tsx";
const source = fs.readFileSync(file, "utf8");

const cp1252 = {
  "€": 0x80, "‚": 0x82, "ƒ": 0x83, "„": 0x84,
  "…": 0x85, "†": 0x86, "‡": 0x87, "ˆ": 0x88,
  "‰": 0x89, "Š": 0x8A, "‹": 0x8B, "Œ": 0x8C,
  "Ž": 0x8E, "‘": 0x91, "’": 0x92, "“": 0x93,
  "”": 0x94, "•": 0x95, "–": 0x96, "—": 0x97,
  "˜": 0x98, "™": 0x99, "š": 0x9A, "›": 0x9B,
  "œ": 0x9C, "ž": 0x9E, "Ÿ": 0x9F
};

function byteOf(ch) {
  const n = ch.charCodeAt(0);

  if (n <= 0x7F) return n;
  if (n >= 0xA0 && n <= 0xFF) return n;

  return cp1252[ch] ?? null;
}

function decodeLine(line) {
  const bytes = [];

  for (const ch of line) {
    const b = byteOf(ch);

    if (b === null) {
      return line;
    }

    bytes.push(b);
  }

  const decoded = Buffer.from(bytes).toString("utf8");

  // ต้องกลายเป็นภาษาไทย และ mojibake ต้องลดลง
  if (
    /[\u0E00-\u0E7F]/.test(decoded) &&
    !/à¸|à¹|â€|Ã|Â/.test(decoded)
  ) {
    return decoded;
  }

  return line;
}

const lines = source.split(/\r?\n/);

let fixed = 0;

const output = lines.map((line) => {
  if (!/[àâÃÂ]/.test(line)) {
    return line;
  }

  const result = decodeLine(line);

  if (result !== line) {
    fixed++;
  }

  return result;
});

fs.writeFileSync(file, output.join("\n"), "utf8");

console.log(`FIXED LINES: ${fixed}`);
console.log("DONE");