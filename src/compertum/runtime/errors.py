class RuntimeRefused(RuntimeError):
    """A closed capability gate; messages never contain private capabilities."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
