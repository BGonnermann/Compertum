class DataError(ValueError):
    """Stable refusal code; never echoes input values into a log."""
    def __init__(self,code):
        self.code=code
        super().__init__(code)
