from typing import Optional

from rich.progress import Progress


class ChunkIterator:
    """
    This iterator cuts down an iterator into several chunks. By example, you
    can iterate over a very long list and do chunk creates every 1000 entry
    using this.
    """

    def __init__(
        self,
        iterable,
        total: Optional[int] = None,
        label: Optional[str] = None,
    ):
        self.iterator = iter(iterable)
        self.total = total
        self.label = label
        self.iterating = True
        self._next = None
        self.iterated = 0

        self.next()

    def next(self):
        nxt = self._next

        try:
            self._next = next(self.iterator)
        except StopIteration:
            self.iterating = False

        return nxt

    def chunks(self, size):
        """
        Call this method to return the chunks iterator
        :param size: int, size of a chunk
        :return:
        """

        def iter_chunk():
            for i in range(0, size):
                yield self.next()
                self.iterated += 1

                if not self.iterating:
                    break

        progress = None
        task = None

        try:

            if self.total is not None:
                progress = Progress()
                task = progress.add_task(self.label or "Iterating", total=self.total)
                progress.start()

            while self.iterating:
                yield iter_chunk()

                if progress:
                    progress.update(task, completed=self.iterated)
        finally:
            if progress:
                progress.stop()
