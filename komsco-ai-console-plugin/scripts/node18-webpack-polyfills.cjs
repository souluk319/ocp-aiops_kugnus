'use strict';

if (!Array.prototype.toSorted) {
  Object.defineProperty(Array.prototype, 'toSorted', {
    configurable: true,
    value(compareFn) {
      return [...this].sort(compareFn);
    },
    writable: true,
  });
}

if (!Array.prototype.toReversed) {
  Object.defineProperty(Array.prototype, 'toReversed', {
    configurable: true,
    value() {
      return [...this].reverse();
    },
    writable: true,
  });
}

if (!Array.prototype.toSpliced) {
  Object.defineProperty(Array.prototype, 'toSpliced', {
    configurable: true,
    value(start, deleteCount, ...items) {
      const copy = [...this];
      copy.splice(start, deleteCount, ...items);
      return copy;
    },
    writable: true,
  });
}
