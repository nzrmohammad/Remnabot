#!/usr/bin/env node
/**
 * Zero-dependency JS minifier for Remnabot TMA frontend assets.
 * Preserves string literals, template literals, and regex literals, strips comments
 * and redundant whitespace/newlines, and verifies every output with Node's vm.Script.
 */
'use strict';

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const JS_DIR = path.resolve(__dirname, '..', 'bot', 'web', 'static', 'js');
const DIST_DIR = path.join(JS_DIR, 'dist');

function minifyJs(src) {
  let out = '';
  let i = 0;
  const n = src.length;
  let lastSig = '';

  const isIdent = ch => /[A-Za-z0-9_$]/.test(ch);
  const canStartRegex = () =>
    lastSig === '' || '([{:;,=!&|?+-*%~^<>'.includes(lastSig) ||
    /(?:^|[^\w$])(return|case|throw|in|of|typeof|delete|void|new|else|do|await|yield)\s*$/.test(out.slice(-16));

  function readTemplateLiteral() {
    out += '`';
    i++;
    while (i < n) {
      const c = src[i];
      if (c === '\\' && i + 1 < n) {
        out += c + src[i + 1];
        i += 2;
        continue;
      }
      if (c === '$' && src[i + 1] === '{') {
        out += '${';
        i += 2;
        lastSig = '{';
        scanChunk(true);
        continue;
      }
      out += c;
      i++;
      if (c === '`') {
        lastSig = '`';
        return;
      }
    }
  }

  function scanChunk(stopAtClosingBrace = false) {
    let braceDepth = stopAtClosingBrace ? 1 : 0;

    while (i < n) {
      const ch = src[i];
      const next = src[i + 1];

      // Line comments
      if (ch === '/' && next === '/') {
        i += 2;
        while (i < n && src[i] !== '\n') i++;
        continue;
      }

      // Block comments
      if (ch === '/' && next === '*') {
        i += 2;
        while (i < n && !(src[i] === '*' && src[i + 1] === '/')) i++;
        i += 2;
        continue;
      }

      // Template literals (preserve whitespace & recursively parse ${...})
      if (ch === '`') {
        readTemplateLiteral();
        continue;
      }

      // Quoted string literals
      if (ch === "'" || ch === '"') {
        const quote = ch;
        let lit = ch;
        i++;
        while (i < n) {
          const c = src[i];
          lit += c;
          i++;
          if (c === '\\' && i < n) {
            lit += src[i];
            i++;
            continue;
          }
          if (c === quote) break;
        }
        out += lit;
        lastSig = quote;
        continue;
      }

      // Regex literals
      if (ch === '/' && canStartRegex()) {
        let rx = ch;
        let inClass = false;
        i++;
        while (i < n) {
          const c = src[i];
          rx += c;
          i++;
          if (c === '\\' && i < n) {
            rx += src[i];
            i++;
            continue;
          }
          if (c === '[') inClass = true;
          else if (c === ']') inClass = false;
          else if (c === '/' && !inClass) break;
          else if (c === '\n') break;
        }
        while (i < n && /[gimsuvy]/.test(src[i])) {
          rx += src[i];
          i++;
        }
        out += rx;
        lastSig = '/';
        continue;
      }

      // Collapse whitespace & preserve ASI newlines conservatively
      if (/\s/.test(ch)) {
        let hasNewline = ch === '\n' || ch === '\r';
        i++;
        while (i < n && /\s/.test(src[i])) {
          if (src[i] === '\n' || src[i] === '\r') hasNewline = true;
          i++;
        }
        const nextCh = src[i] || '';
        if (!out || !nextCh) continue;
        const prevCh = out[out.length - 1];
        if (hasNewline) {
          if (!';{([,?:'.includes(prevCh) && !'}).,;:]'.includes(nextCh)) {
            out += '\n';
            lastSig = '\n';
          }
        } else if (
          (isIdent(prevCh) && isIdent(nextCh)) ||
          (prevCh === '+' && nextCh === '+') ||
          (prevCh === '-' && nextCh === '-')
        ) {
          out += ' ';
        }
        continue;
      }

      if (stopAtClosingBrace) {
        if (ch === '{') braceDepth++;
        else if (ch === '}') {
          braceDepth--;
          out += ch;
          lastSig = ch;
          i++;
          if (braceDepth === 0) return;
          continue;
        }
      }

      out += ch;
      lastSig = ch;
      i++;
    }
  }

  scanChunk(false);
  return out.trim() + '\n';
}

function main() {
  fs.mkdirSync(DIST_DIR, { recursive: true });
  const files = fs
    .readdirSync(JS_DIR)
    .filter(f => f.endsWith('.js') && !f.endsWith('.min.js'))
    .sort();

  let totalRaw = 0;
  let totalMin = 0;
  for (const fname of files) {
    const raw = fs.readFileSync(path.join(JS_DIR, fname), 'utf8');
    const min = minifyJs(raw);
    new vm.Script(min, { filename: `${fname}.min.js` });
    const outPath = path.join(DIST_DIR, fname.replace(/\.js$/, '.min.js'));
    fs.writeFileSync(outPath, min, 'utf8');
    totalRaw += Buffer.byteLength(raw, 'utf8');
    totalMin += Buffer.byteLength(min, 'utf8');
  }

  const pct = totalRaw > 0 ? (((totalRaw - totalMin) / totalRaw) * 100).toFixed(1) : '0.0';
  console.log(`Minified ${files.length} JS files: ${(totalRaw / 1024).toFixed(1)} KB -> ${(totalMin / 1024).toFixed(1)} KB (-${pct}%)`);
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  main();
}
export { minifyJs };
