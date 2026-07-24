// Thai word segmentation via ICU. stdin: JSON array of lines. stdout: JSON array of word-arrays.
// Each line's words concatenate back to the exact original line.
import { readFileSync } from 'node:fs';

const lines = JSON.parse(readFileSync(0, 'utf8'));
const seg = new Intl.Segmenter('th', { granularity: 'word' });

const out = lines.map(line => {
  const words = [];
  for (const s of seg.segment(line)) words.push(s.segment);
  const joined = words.join('');
  if (joined !== line) {
    process.stderr.write(`SEGMENT MISMATCH: ${JSON.stringify(line)} -> ${JSON.stringify(joined)}\n`);
    process.exit(1);
  }
  return words;
});
process.stdout.write(JSON.stringify(out));
