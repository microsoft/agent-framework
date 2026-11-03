// Copyright (c) Microsoft. All rights reserved.

const assert = require('node:assert/strict');
const fs = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { afterEach, beforeEach, describe, it } = require('node:test');
const stageBundle = require('../scripts/gaw-issue-triage-bundle.js');

describe('Checked issue triage bundles', () => {
  let directory;
  let source;
  let destination;
  let input;
  beforeEach(() => {
    directory = fs.mkdtempSync(join(tmpdir(), 'triage-bundle-'));
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
    assert.equal(stageBundle(input), true);
    assert.equal(fs.readdirSync(destination).length, 1000);
    assert.equal(fs.statSync(join(destination, 'test.txt')).size, 10 * 1024 * 1024);
    assert.equal(fs.existsSync(join(destination, 'unrelated-secret')), false);
  });

  it('rejects excessive bytes or file counts before creating an upload copy', () => {
    fs.writeFileSync(join(source, 'large'), '');
    fs.truncateSync(join(source, 'large'), 10 * 1024 * 1024 + 1);
    assert.throws(() => stageBundle(input), /10 MiB/);
    assert.equal(fs.existsSync(destination), false);
    fs.unlinkSync(join(source, 'large'));
    for (let i = 0; i < 1000; i++) fs.writeFileSync(join(source, `empty-${i}`), '');
    assert.throws(() => stageBundle(input), /1,000 files/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('bounds empty folders and path metadata as well as file contents', () => {
    for (let i = 0; i < 2000; i++) fs.mkdirSync(join(source, `empty-${i}`));
    assert.throws(() => stageBundle(input), /folder or path metadata/);
    const deep = join(directory, 'deep');
    const nested = join(deep, ...Array(40).fill('d'.repeat(40)));
    fs.mkdirSync(nested, { recursive: true });
    for (let i = 0; i < 700; i++) fs.writeFileSync(join(nested, `file-${i}`), '');
    assert.throws(() => stageBundle({ ...input, source: deep }), /folder or path metadata/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('rejects symbolic links, hard links, and linked ancestor folders', () => {
    fs.symlinkSync(join(directory, 'outside'), join(source, 'link'));
    assert.throws(() => stageBundle(input), /not links/);
    fs.unlinkSync(join(source, 'link'));
    fs.writeFileSync(join(directory, 'outside'), 'private');
    fs.linkSync(join(directory, 'outside'), join(source, 'hardlink'));
    assert.throws(() => stageBundle(input), /not links/);
    fs.unlinkSync(join(source, 'hardlink'));
    const alias = join(directory, 'alias');
    fs.symlinkSync(directory, alias);
    assert.throws(() => stageBundle({ ...input, source: join(alias, 'source') }), /not links/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('allows absence but rejects a nonempty bundle without a current report', () => {
    assert.equal(stageBundle({ ...input, source: join(directory, 'missing') }), false);
    fs.unlinkSync(join(source, 'report.md'));
    assert.equal(stageBundle(input), false);
    fs.writeFileSync(join(source, 'old-record.json'), '{}');
    assert.throws(() => stageBundle(input), /current report.md/);
    assert.equal(fs.existsSync(destination), false);
  });

  it('rejects names that could become archive path separators or control characters', () => {
    for (const name of ['..\\outside', 'line\nbreak']) {
      fs.writeFileSync(join(source, name), 'data');
      assert.throws(() => stageBundle(input), /backslashes or control characters/);
      assert.equal(fs.existsSync(destination), false);
      fs.unlinkSync(join(source, name));
    }
  });
});
