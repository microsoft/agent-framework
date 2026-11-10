// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { afterEach, beforeEach, describe, it } = require('node:test');
const checkEvidenceFiles = require('../scripts/issue-routing-evidence.js');

describe('Evidence file checks', () => {
  let directory;
  let source;
  let destination;
  let input;
  beforeEach(() => {
    directory = fs.mkdtempSync(join(tmpdir(), 'evidence-check-'));
    source = join(directory, 'source');
    destination = join(directory, 'checked');
    fs.mkdirSync(source);
    fs.writeFileSync(join(source, 'report.md'), '');
    input = { source, destination, core: { info() {} } };
  });
  afterEach(() => fs.rmSync(directory, { recursive: true, force: true }));

  it('allows the exact byte and file limits and copies only the selected evidence', () => {
    fs.writeFileSync(join(source, 'test.txt'), Buffer.alloc(10 * 1024 * 1024));
    for (let i = 0; i < 998; i++) fs.writeFileSync(join(source, `empty-${i}`), '');
    fs.writeFileSync(join(directory, 'unrelated-secret'), 'must not be copied');
    assert.equal(checkEvidenceFiles(input), true);
    assert.equal(fs.readdirSync(destination).length, 1000);
    assert.equal(fs.statSync(join(destination, 'test.txt')).size, 10 * 1024 * 1024);
    assert.equal(fs.existsSync(join(destination, 'unrelated-secret')), false);
  });

  it('rejects excessive bytes or file counts before creating an upload copy', () => {
    fs.writeFileSync(join(source, 'large'), '');
    fs.truncateSync(join(source, 'large'), 10 * 1024 * 1024 + 1);
    assert.throws(() => checkEvidenceFiles(input), /10 MiB/);
    assert.equal(fs.existsSync(destination), false);
    fs.unlinkSync(join(source, 'large'));
    for (let i = 0; i < 1000; i++) fs.writeFileSync(join(source, `empty-${i}`), '');
    assert.throws(() => checkEvidenceFiles(input), /1,000 files/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('bounds empty folders and path metadata as well as file contents', () => {
    for (let i = 0; i < 2000; i++) fs.mkdirSync(join(source, `empty-${i}`));
    assert.throws(() => checkEvidenceFiles(input), /folders or path name length/);
    const deep = join(directory, 'deep');
    const nested = join(deep, ...Array(40).fill('d'.repeat(40)));
    fs.mkdirSync(nested, { recursive: true });
    for (let i = 0; i < 700; i++) fs.writeFileSync(join(nested, `file-${i}`), '');
    assert.throws(() => checkEvidenceFiles({ ...input, source: deep }), /folders or path name length/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('rejects symbolic links, hard links, and linked ancestor folders', () => {
    fs.symlinkSync(join(directory, 'outside'), join(source, 'link'));
    assert.throws(() => checkEvidenceFiles(input), /not links/);
    fs.unlinkSync(join(source, 'link'));
    fs.writeFileSync(join(directory, 'outside'), 'private');
    fs.linkSync(join(directory, 'outside'), join(source, 'hardlink'));
    assert.throws(() => checkEvidenceFiles(input), /not links/);
    fs.unlinkSync(join(source, 'hardlink'));
    const alias = join(directory, 'alias');
    fs.symlinkSync(directory, alias);
    assert.throws(() => checkEvidenceFiles({ ...input, source: join(alias, 'source') }), /not links/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('allows absence but rejects nonempty evidence without a current report', () => {
    assert.equal(checkEvidenceFiles({ ...input, source: join(directory, 'missing') }), false);
    fs.unlinkSync(join(source, 'report.md'));
    assert.equal(checkEvidenceFiles(input), false);
    fs.writeFileSync(join(source, 'old-record.json'), '{}');
    assert.throws(() => checkEvidenceFiles(input), /current report.md/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('rejects names that could become archive path separators or control characters', () => {
    for (const name of ['..\\outside', 'line\nbreak']) {
      fs.writeFileSync(join(source, name), 'data');
      assert.throws(() => checkEvidenceFiles(input), /backslashes or control characters/);
      assert.equal(fs.existsSync(destination), false);
      fs.unlinkSync(join(source, name));
    }
  });
});
