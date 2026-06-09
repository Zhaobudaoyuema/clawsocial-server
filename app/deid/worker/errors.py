"""Worker router exceptions."""


class WorkerError(Exception):
    """Base worker error."""


class WorkerOffline(WorkerError):
    """No worker connected."""


class WorkerBusy(WorkerError):
    """Worker state is not ready."""


class WorkerRequestError(WorkerError):
    """Worker or Ollama returned an error response."""

    def __init__(self, status: int, body: object):
        self.status = status
        self.body = body
        super().__init__(f"worker request failed: status={status}")
