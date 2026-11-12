#!/usr/bin/env python3
"""Minimal read-only MCP-style stdio server for the local RAG index.

Implements JSON-RPC methods needed by MCP clients: initialize, tools/list,
and tools/call. It intentionally exposes no mutation or shell execution.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from rag_index import search

DB = Path('.rag/index.sqlite')


def response(request_id, result):
    return {'jsonrpc': '2.0', 'id': request_id, 'result': result}


def error(request_id, code, message):
    return {'jsonrpc': '2.0', 'id': request_id,
            'error': {'code': code, 'message': message}}


def call_tool(name, arguments):
    if name == 'search_repository':
        query = str(arguments.get('query', '')).strip()
        if not query:
            raise ValueError('query is required')
        return {'content': [{'type': 'text', 'text': json.dumps(
            search(DB, query, int(arguments.get('limit', 8))), indent=2)}]}
    if name == 'architecture_status':
        return {'content': [{'type': 'text', 'text': json.dumps({
            'database': str(DB),
            'tools': ['search_repository'],
            'mutations': False,
            'scope': 'repository source, documentation, and indexed evidence'
        }, indent=2)}]}
    raise ValueError(f'unknown tool: {name}')


def handle(request):
    request_id = request.get('id')
    method = request.get('method')
    if method == 'initialize':
        return response(request_id, {
            'protocolVersion': request.get('params', {}).get('protocolVersion', '2024-11-05'),
            'capabilities': {'tools': {}},
            'serverInfo': {'name': 'ever-rag', 'version': '0.1.0'},
        })
    if method == 'notifications/initialized':
        return None
    if method == 'tools/list':
        return response(request_id, {'tools': [
            {'name': 'search_repository',
             'description': 'Search indexed repository code, docs, and evidence.',
             'inputSchema': {'type': 'object', 'required': ['query'],
                             'properties': {'query': {'type': 'string'},
                                            'limit': {'type': 'integer', 'default': 8}}}},
            {'name': 'architecture_status',
             'description': 'Return the read-only RAG server status.',
             'inputSchema': {'type': 'object', 'properties': {}}},
        ]})
    if method == 'tools/call':
        params = request.get('params', {})
        try:
            return response(request_id, call_tool(params['name'], params.get('arguments', {})))
        except (KeyError, ValueError) as exc:
            return error(request_id, -32602, str(exc))
    return error(request_id, -32601, f'unsupported method: {method}')


def main():
    for line in sys.stdin:
        try:
            result = handle(json.loads(line))
            if result is not None:
                print(json.dumps(result), flush=True)
        except json.JSONDecodeError as exc:
            print(json.dumps(error(None, -32700, str(exc))), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
