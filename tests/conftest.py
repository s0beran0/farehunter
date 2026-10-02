import os
import tempfile

# Testes nunca tocam na pasta de dados real do usuário.
os.environ.setdefault("FAREHUNTER_DATA", tempfile.mkdtemp(prefix="farehunter-teste-"))
