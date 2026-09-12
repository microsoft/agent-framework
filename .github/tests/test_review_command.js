// Copyright (c) Microsoft. All rights reserved.

/**
 * Tests for review_command.js.
 *
 * Run with: node --test .github/tests/test_review_command.js
 */

const { describe, it } = require('node:test');
const assert = require('node:assert/strict');

const isReviewCommand = require('../scripts/review_command.js');


describe('review command validation', () => {
  it('accepts the exact review command', () => {
    assert.equal(isReviewCommand('/review'), true);
  });

  it('accepts surrounding whitespace', () => {
    assert.equal(isReviewCommand('/review\r\n'), true);
    assert.equal(isReviewCommand('  \n/review\t'), true);
  });

  it('rejects commands with additional content', () => {
    assert.equal(isReviewCommand('/reviewer'), false);
    assert.equal(isReviewCommand('/review please'), false);
    assert.equal(isReviewCommand('/review\nadditional text'), false);
    assert.equal(isReviewCommand('/Review'), false);
  });

  it('rejects missing or non-string comment bodies', () => {
    assert.equal(isReviewCommand(''), false);
    assert.equal(isReviewCommand(null), false);
    assert.equal(isReviewCommand(undefined), false);
  });
});
