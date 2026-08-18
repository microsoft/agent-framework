// Copyright (c) Microsoft. All rights reserved.

const BREAKING_CHANGE_LABEL = 'breaking change';
const BREAKING_PREFIX = '[BREAKING]';

const DEFAULT_PREFIX_LABELS = Object.freeze({
  python: 'Python',
  '.NET': '.NET',
});

const DEFAULT_BRACKET_PREFIX_LABELS = Object.freeze({
  [BREAKING_CHANGE_LABEL]: BREAKING_PREFIX,
});

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function getMatchingValueByKey(valuesByKey, keyToFind) {
  const matchingKey = Object.keys(valuesByKey).find((key) => key.toLowerCase() === keyToFind.toLowerCase());
  return matchingKey === undefined ? null : valuesByKey[matchingKey];
}

function getPrefixPattern(prefixes) {
  return prefixes.map(escapeRegExp).join('|');
}

function canonicalizePrefix(prefix, prefixes) {
  return prefixes.find((knownPrefix) => knownPrefix.toLowerCase() === prefix.toLowerCase()) ?? prefix;
}

function normalizeLeadingBracketPrefix(title, bracketPrefixes) {
  const bracketPattern = getPrefixPattern(bracketPrefixes);
  if (!bracketPattern) {
    return title;
  }

  const leadingBracketPrefix = new RegExp(`^(${bracketPattern})(?=\\s|$)`, 'i');
  return title.replace(
    leadingBracketPrefix,
    (bracketPrefix) => canonicalizePrefix(bracketPrefix, bracketPrefixes),
  );
}

function parseLeadingTitlePrefix(title, titlePrefixes) {
  const titlePrefixPattern = getPrefixPattern(titlePrefixes);
  if (!titlePrefixPattern) {
    return null;
  }

  const match = title.match(new RegExp(`^(${titlePrefixPattern}):\\s*`, 'i'));
  if (!match) {
    return null;
  }

  return {
    prefix: canonicalizePrefix(match[1], titlePrefixes),
    rest: title.slice(match[0].length).trimStart(),
  };
}

function removeBracketPrefixToken(title, bracketPrefix) {
  const bracketPrefixPattern = escapeRegExp(bracketPrefix);
  return title
    .replace(new RegExp(`(^|\\s+)${bracketPrefixPattern}(?=\\s|$)`, 'ig'), '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function addTitlePrefix(title, prefix, bracketPrefixes = Object.values(DEFAULT_BRACKET_PREFIX_LABELS)) {
  const bracketPattern = getPrefixPattern(bracketPrefixes);
  const prefixPattern = escapeRegExp(prefix);

  if (bracketPattern) {
    const bracketThenTitlePrefix = new RegExp(`^(${bracketPattern})(\\s+)(${prefixPattern})(?=:)`, 'i');
    if (bracketThenTitlePrefix.test(title)) {
      return title.replace(
        bracketThenTitlePrefix,
        (match, bracketPrefix, spacing) => `${canonicalizePrefix(bracketPrefix, bracketPrefixes)}${spacing}${prefix}`,
      );
    }

    title = normalizeLeadingBracketPrefix(title, bracketPrefixes);
  }

  if (!title.startsWith(`${prefix}: `)) {
    const existingTitlePrefix = new RegExp(`^${prefixPattern}:\\s*`, 'i');
    if (existingTitlePrefix.test(title)) {
      return title.replace(existingTitlePrefix, `${prefix}: `);
    }

    return `${prefix}: ${title}`;
  }

  return title;
}

function hasBracketPrefix(title, bracketPrefix, titlePrefixes = Object.values(DEFAULT_PREFIX_LABELS)) {
  const bracketPrefixPattern = escapeRegExp(bracketPrefix);
  const leadingBracketPrefix = new RegExp(`^${bracketPrefixPattern}(?=\\s|$)`, 'i');
  if (leadingBracketPrefix.test(title)) {
    return true;
  }

  const leadingTitlePrefix = parseLeadingTitlePrefix(title, titlePrefixes);
  if (!leadingTitlePrefix) {
    return false;
  }

  return leadingBracketPrefix.test(leadingTitlePrefix.rest);
}

function addBracketPrefix(title, bracketPrefix, titlePrefixes = Object.values(DEFAULT_PREFIX_LABELS)) {
  const bracketPrefixPattern = escapeRegExp(bracketPrefix);
  const leadingBracketPrefix = new RegExp(`^${bracketPrefixPattern}(?=\\s|$)`, 'i');
  if (leadingBracketPrefix.test(title)) {
    return title.replace(leadingBracketPrefix, bracketPrefix);
  }

  const leadingTitlePrefix = parseLeadingTitlePrefix(title, titlePrefixes);
  if (leadingTitlePrefix) {
    if (leadingBracketPrefix.test(leadingTitlePrefix.rest)) {
      const normalizedRest = leadingTitlePrefix.rest.replace(leadingBracketPrefix, bracketPrefix);
      return `${leadingTitlePrefix.prefix}: ${normalizedRest}`;
    }

    const titleWithoutBracketPrefix = removeBracketPrefixToken(leadingTitlePrefix.rest, bracketPrefix);
    return `${leadingTitlePrefix.prefix}: ${bracketPrefix}`
      + (titleWithoutBracketPrefix ? ` ${titleWithoutBracketPrefix}` : '');
  }

  const titleWithoutBracketPrefix = removeBracketPrefixToken(title, bracketPrefix);
  return `${bracketPrefix}${titleWithoutBracketPrefix ? ` ${titleWithoutBracketPrefix}` : ''}`;
}

function hasLabel(labels, labelName) {
  return labels.some((label) => label.toLowerCase() === labelName.toLowerCase());
}

function getCurrentTitle(context) {
  switch (context.eventName) {
    case 'issues':
      return context.payload.issue.title;
    case 'pull_request_target':
      return context.payload.pull_request.title;
    default:
      throw new Error(`Unrecognized eventName: ${context.eventName}`);
  }
}

async function updateTitleForAddedLabel({
  github,
  context,
  core,
  prefixLabels = DEFAULT_PREFIX_LABELS,
  bracketPrefixLabels = DEFAULT_BRACKET_PREFIX_LABELS,
}) {
  const labelAdded = context.payload.label?.name;
  if (!labelAdded) {
    throw new Error('This script must be run from a labeled event.');
  }

  const currentTitle = getCurrentTitle(context);
  let newTitle = null;

  const titlePrefix = getMatchingValueByKey(prefixLabels, labelAdded);
  if (titlePrefix !== null) {
    newTitle = addTitlePrefix(currentTitle, titlePrefix, Object.values(bracketPrefixLabels));
  }

  const bracketPrefix = getMatchingValueByKey(bracketPrefixLabels, labelAdded);
  if (bracketPrefix !== null) {
    newTitle = addBracketPrefix(currentTitle, bracketPrefix, Object.values(prefixLabels));
  }

  if (newTitle === null) {
    core.info(`No title prefix configured for label "${labelAdded}".`);
    return { updated: false, newTitle: currentTitle };
  }

  if (newTitle === currentTitle) {
    core.info(`Title already includes the prefix for label "${labelAdded}".`);
    return { updated: false, newTitle };
  }

  switch (context.eventName) {
    case 'issues':
      await github.rest.issues.update({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        title: newTitle,
      });
      break;

    case 'pull_request_target':
      await github.rest.pulls.update({
        pull_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        title: newTitle,
      });
      break;

    default:
      throw new Error(`Unrecognized eventName: ${context.eventName}`);
  }

  return { updated: true, newTitle };
}

async function syncBreakingChangeLabelFromTitle({
  github,
  context,
  core,
  labelName = BREAKING_CHANGE_LABEL,
  bracketPrefix = BREAKING_PREFIX,
  titlePrefixes = Object.values(DEFAULT_PREFIX_LABELS),
}) {
  const pullRequest = context.payload.pull_request;
  if (!pullRequest) {
    throw new Error('This script must be run from a pull_request_target event.');
  }

  const title = pullRequest.title || '';
  if (!hasBracketPrefix(title, bracketPrefix, titlePrefixes)) {
    core.info(`Title does not include ${bracketPrefix} in the title prefix.`);
    return { added: false };
  }

  const labels = pullRequest.labels?.map((label) => label.name).filter(Boolean) ?? [];
  if (hasLabel(labels, labelName)) {
    core.info(`PR already has the "${labelName}" label.`);
    return { added: false };
  }

  await github.rest.issues.addLabels({
    issue_number: context.issue.number,
    owner: context.repo.owner,
    repo: context.repo.repo,
    labels: [labelName],
  });

  return { added: true };
}

module.exports = {
  addBracketPrefix,
  addTitlePrefix,
  hasBracketPrefix,
  syncBreakingChangeLabelFromTitle,
  updateTitleForAddedLabel,
};
