function abortError(signal: AbortSignal): unknown {
  return signal.reason ?? new DOMException("The operation was aborted.", "AbortError");
}

function nextWithSignal<T>(iterator: AsyncIterator<T>, signal: AbortSignal): Promise<IteratorResult<T>> {
  signal.throwIfAborted();
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      signal.removeEventListener("abort", onAbort);
      reject(abortError(signal));
    };
    signal.addEventListener("abort", onAbort, { once: true });
    void iterator.next().then(
      (result) => {
        signal.removeEventListener("abort", onAbort);
        resolve(result);
      },
      (error: unknown) => {
        signal.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

export async function* abortableAsyncIterable<T>(
  source: AsyncIterable<T>,
  signal: AbortSignal | undefined,
): AsyncGenerator<T> {
  if (signal === undefined) {
    yield* source;
    return;
  }

  const iterator = source[Symbol.asyncIterator]();
  let complete = false;
  try {
    while (true) {
      const result = await nextWithSignal(iterator, signal);
      signal.throwIfAborted();
      if (result.done) {
        complete = true;
        return;
      }
      yield result.value;
      signal.throwIfAborted();
    }
  } finally {
    if (!complete && iterator.return !== undefined) {
      const cleanup = iterator.return();
      if (signal.aborted) {
        void cleanup.catch(() => undefined);
      } else {
        await cleanup;
      }
    }
  }
}
