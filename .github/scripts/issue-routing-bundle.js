// Copyright (c) Microsoft. All rights reserved.

const fs = require('node:fs');
const path = require('node:path');

// Check files as data and prepare an upload copy, without executing their contents.
// Used before the temporary transfer and again after the publishing job downloads it.
function stageBundle({ source, destination, core }) {
  const root = path.resolve(source);
  let parent = path.parse(root).root;
  // Check ancestors too: a link above the bundle must not redirect a host read.
  for (const component of root.slice(parent.length).split(path.sep)) {
    parent = path.join(parent, component);
    const stat = fs.lstatSync(parent, { throwIfNoEntry: false });
    if (!stat) {
      core.info('No current routing bundle was saved.');
      return false;
    }
    if (!stat.isDirectory() || stat.isSymbolicLink()) {
      throw new Error('Routing bundle paths must be directories, not links.');
    }
  }

  // Inspect the whole bundle before copying anything. Empty folders and long paths
  // consume archive space too, even when the file contents are small.
  const files = [];
  let entries = 0;
  let bytes = 0;
  let pathBytes = 0;
  function collect(directory) {
    const handle = fs.opendirSync(directory);
    try {
      let entry;
      while ((entry = handle.readSync()) !== null) {
        if (/[\\\x00-\x1f]/.test(entry.name)) {
          throw new Error('Routing filenames must not contain backslashes or control characters.');
        }
        const file = path.join(directory, entry.name);
        const relative = path.relative(root, file);
        pathBytes += Buffer.byteLength(relative);
        if (++entries > 2000 || pathBytes > 1024 * 1024) {
          throw new Error('Routing bundle exceeds the folder or path metadata limit.');
        }
        const stat = fs.lstatSync(file);
        if (stat.isDirectory()) {
          collect(file);
        } else if (stat.isFile() && stat.nlink === 1) {
          bytes += stat.size;
          if (bytes > 10 * 1024 * 1024 || files.length >= 1000) {
            throw new Error('Routing bundle exceeds 10 MiB or 1,000 files.');
          }
          files.push({ file, relative, size: stat.size });
        } else {
          throw new Error('Routing bundles may contain only ordinary files and directories, not links.');
        }
      }
    } finally {
      handle.closeSync();
    }
  }
  collect(root);
  if (!files.length) {
    core.info('The current routing bundle has no files.');
    return false;
  }
  // Retained history still needs a report describing the current run's findings.
  if (!files.some(file => file.relative === 'report.md')) {
    throw new Error('Routing bundles require a current report.md.');
  }

  // Callers place this fresh copy outside the agent's writable folders.
  // Upload steps may use it only after the entire check and copy succeeds.
  const buffer = Buffer.alloc(64 * 1024);
  let copied = 0;
  for (const file of files) {
    const target = path.join(destination, file.relative);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    // Do not follow a new link or wait on a file that changed into a pipe.
    const input = fs.openSync(file.file, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW | fs.constants.O_NONBLOCK);
    try {
      const stat = fs.fstatSync(input);
      if (!stat.isFile() || stat.nlink !== 1) {
        throw new Error('Routing evidence changed into a link or unsupported file.');
      }
      const output = fs.openSync(target, 'wx', 0o600);
      try {
        let length;
        let fileBytes = 0;
        // Bound actual reads as well as file metadata before allowing any upload.
        while ((length = fs.readSync(input, buffer)) !== 0) {
          copied += length;
          fileBytes += length;
          if (copied > 10 * 1024 * 1024 || fileBytes > file.size) {
            throw new Error('Routing evidence grew beyond its checked size.');
          }
          fs.writeFileSync(output, buffer.subarray(0, length));
        }
        if (fileBytes !== file.size) throw new Error('Routing evidence changed while preparing the upload.');
      } finally {
        fs.closeSync(output);
      }
    } finally {
      fs.closeSync(input);
    }
  }
  core.info(`Checked ${files.length} routing files (${copied} bytes).`);
  return true;
}

module.exports = stageBundle;
