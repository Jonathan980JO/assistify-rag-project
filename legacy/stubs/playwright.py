class Dummy:
    def __init__(self, *a, **k):
        pass

def sync_playwright():
    class Ctx:
        def __enter__(self):
            return Dummy()
        def __exit__(self, *a):
            return False
    return Ctx()
