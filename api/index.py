"""Entrypoint serverless do Vercel.

O runtime Python do Vercel usa a variavel `handler` (subclasse de
BaseHTTPRequestHandler). Reaproveitamos o mesmo Handler do servidor local.
Todas as rotas caem aqui (ver rewrites no vercel.json).
"""
import os
import sys

# Garante que o pacote `mithrandir` (na raiz do repo) seja importavel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mithrandir.server import Handler as handler  # noqa: E402,F401
