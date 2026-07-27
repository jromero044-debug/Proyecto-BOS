"""
Servidor MCP standalone para COCEO — expone el contexto ejecutivo de MiradorCT BOS
(entries, meetings, decisions, projects, operacional) como tools para Claude.

No forma parte del deploy de Azure Functions. Corre local via stdio, invocado por
el cliente MCP (ej. Claude Desktop), que le pasa COCEO_SECRET_KEY por env.

Requiere Python >=3.10 (venv dedicado: .venv-mcp, separado del .venv del Function App
que está pinneado a 3.9 por compat con Azure).
"""
import os

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

COCEO_BASE_URL = os.environ.get("COCEO_BASE_URL", "https://mirador-bos-prod.azurewebsites.net/api")
COCEO_KEY = os.environ.get("COCEO_SECRET_KEY", "")
COCEO_BRAND = os.environ.get("COCEO_BRAND", "cebala")

HEADERS = {"x-coceo-key": COCEO_KEY, "Content-Type": "application/json"}

server = Server("coceo")

TOOLS = [
    Tool(
        name="coceo_context",
        description="Trae el contexto ejecutivo completo: entries, meetings, decisions, projects y followups recientes/pendientes.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="coceo_pending",
        description="Trae decisions y followups pendientes (abiertos), ordenados por fecha límite.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Máximo de registros a traer (default 20)"},
            },
        },
    ),
    Tool(
        name="coceo_save_entry",
        description="Guarda una entrada libre de contexto ejecutivo (nota, idea, observación).",
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Contenido de la entrada"},
                "type": {"type": "string", "description": "Tipo de entrada (nota, idea, alerta, etc.)"},
                "summary": {"type": "string"},
                "tags": {"type": "string"},
                "priority": {"type": "string", "description": "low, medium, high"},
            },
            "required": ["content"],
        },
    ),
    Tool(
        name="coceo_save_meeting",
        description="Guarda el resumen de una reunión: asistentes, agenda, decisiones y acciones.",
        inputSchema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Fecha YYYY-MM-DD"},
                "attendees": {"type": "string"},
                "summary": {"type": "string"},
                "agenda": {"type": "string"},
                "decisions": {"type": "string"},
                "action_items": {"type": "string"},
            },
            "required": ["summary"],
        },
    ),
    Tool(
        name="coceo_save_decision",
        description="Guarda una decisión ejecutiva con su racional y próximo paso.",
        inputSchema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "decision": {"type": "string"},
                "rationale": {"type": "string"},
                "next_step": {"type": "string"},
                "due_date": {"type": "string", "description": "Fecha YYYY-MM-DD"},
                "status": {"type": "string", "description": "open, executing, done"},
            },
            "required": ["title", "decision"],
        },
    ),
    Tool(
        name="coceo_save_project",
        description="Guarda o actualiza un proyecto activo.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "ID del proyecto si es una actualización"},
                "title": {"type": "string"},
                "status": {"type": "string", "description": "active, paused, done"},
                "start_date": {"type": "string"},
                "target_date": {"type": "string"},
                "summary": {"type": "string"},
                "last_update": {"type": "string"},
            },
            "required": ["title"],
        },
    ),
    Tool(
        name="coceo_save_operacional",
        description="Guarda una entrada operacional asociada a un local (sucursal).",
        inputSchema={
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "local_id": {"type": "integer", "description": "ID del local"},
                "type": {"type": "string"},
                "summary": {"type": "string"},
                "tags": {"type": "string"},
                "priority": {"type": "string"},
            },
            "required": ["content", "local_id"],
        },
    ),
    Tool(
        name="coceo_empresa",
        description="Trae información general de la empresa (marca, locales, estructura).",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="coceo_locales",
        description="Lista los locales (sucursales) registrados.",
        inputSchema={"type": "object", "properties": {}},
    ),
]

_ENDPOINTS = {
    "coceo_context": ("GET", "/coceo/context"),
    "coceo_pending": ("GET", "/coceo/pending"),
    "coceo_save_entry": ("POST", "/coceo/entry"),
    "coceo_save_meeting": ("POST", "/coceo/meeting"),
    "coceo_save_decision": ("POST", "/coceo/decision"),
    "coceo_save_project": ("POST", "/coceo/project"),
    "coceo_save_operacional": ("POST", "/coceo/operacional"),
    "coceo_empresa": ("GET", "/coceo/empresa"),
    "coceo_locales": ("GET", "/coceo/locales"),
}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name not in _ENDPOINTS:
        return [TextContent(type="text", text=f"Tool desconocida: {name}")]

    method, path = _ENDPOINTS[name]
    url = f"{COCEO_BASE_URL}{path}"
    params = {"brand": COCEO_BRAND}

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if method == "GET":
                if name == "coceo_pending" and arguments.get("limit"):
                    params["limit"] = arguments["limit"]
                r = await client.get(url, headers=HEADERS, params=params)
            else:
                r = await client.post(url, headers=HEADERS, params=params, json=arguments)
    except httpx.RequestError as e:
        return [TextContent(type="text", text=f"Error de conexión con COCEO ({url}): {e}")]

    return [TextContent(type="text", text=r.text)]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
