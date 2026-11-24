class UserError(Exception):
    """A problem the user can fix (bad input, missing key, unreadable page)."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
