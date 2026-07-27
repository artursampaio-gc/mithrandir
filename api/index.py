"""Entrypoint serverless do Vercel.

O runtime Python do Vercel (@vercel/python) procura, no topo do arquivo, uma
classe/variavel chamada `handler` (subclasse de BaseHTTPRequestHandler),
`app` ou `application`. Definimos `handler` como subclasse do Handler do
servidor local para o detector reconhece-lo. Todas as rotas caem aqui
(ver routes no vercel.json).
"""
import os
import sys

# Garante que o pacote `mithrandir` (na raiz do repo) seja importavel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mithrandir.server import Handler  # noqa: E402


class handler(Handler):  # noqa: N801  (nome exigido pelo Vercel)
    pass
