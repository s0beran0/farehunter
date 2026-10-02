import os
import tempfile

# Tests never touch the user's real data folder.
os.environ.setdefault("FAREHUNTER_DATA", tempfile.mkdtemp(prefix="farehunter-teste-"))
