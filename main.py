"""
main.py — Punto de entrada del servidor.
Ejecutar con: python main.py
"""
import os
import sys
import uvicorn

# Asegurar que el directorio raíz esté en el path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api_server import app
from backend.config import config

if __name__ == "__main__":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("=" * 60)
    print(f"  {config.tournament_name}")
    print("  Sistema de Torneo Fortnite - Importacion de Replays")
    print("=" * 60)
    print(f"  Pagina publica: http://localhost:{config.server_port}")
    print(f"  Dashboard admin: http://localhost:{config.server_port}/admin")
    print(f"  Clasificacion publica: http://localhost:{config.server_port}/public")
    print(f"  API:       http://localhost:{config.server_port}/api")
    print("=" * 60)
    print()
    print("  Presiona Ctrl+C para detener el servidor")
    print()
    print("  Presiona Ctrl+C para detener el servidor")
    print()

    uvicorn.run(
        "backend.api_server:app",
        host=config.server_host,
        port=config.server_port,
        reload=False,
        log_level="warning",
    )
