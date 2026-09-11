"""Explicit per-cell failures; device recovery errors also quarantine a target."""


class CellFailure(RuntimeError):
    def __init__(self, status, stage, detail, *, target_unusable=False):
        super().__init__(detail)
        self.status = status
        self.stage = stage
        self.detail = detail
        self.target_unusable = target_unusable
