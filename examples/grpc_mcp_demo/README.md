# gRPC + MCP demo

This example shows how to expose a tiny gRPC job board to the Model Context Protocol (MCP).

## Components
- **gRPC server** (`grpc_server.py`): Implements `CreateJob`, `GetJob`, and `DeleteJob` RPCs with an in-memory store.
- **MCP server** (`mcp_server.py`): Wraps the gRPC API as MCP tools so LLMs can call it.

## Generate gRPC stubs
The generated `job_pb2.py` and `job_pb2_grpc.py` files were created with:

```bash
python -m grpc_tools.protoc -I=examples/grpc_mcp_demo --python_out=. --grpc_python_out=. examples/grpc_mcp_demo/job.proto
```

## Run the gRPC server

```bash
python examples/grpc_mcp_demo/grpc_server.py
```

The server listens on port `50051` by default.

## Run the MCP server

```bash
python examples/grpc_mcp_demo/mcp_server.py
```

The MCP server connects to `localhost:50051` by default. You can override the target per-tool by passing an `address` argument.

## Run everything with Docker Compose

Build and start both the gRPC backend and MCP server with one command:

```bash
cd examples/grpc_mcp_demo
docker compose up --build
```

- gRPC will be available on `localhost:50051` inside the Docker network and exposed to the host on the same port.
- The MCP server runs with SSE transport on `http://localhost:8765/sse` so an LLM client can connect to it directly.

You can customize the behavior with environment variables in `docker-compose.yml`:

- `GRPC_TARGET`: Address the MCP server should call (defaults to the gRPC service name `grpc:50051`).
- `MCP_HOST`: Interface the MCP server binds to (default `0.0.0.0` in Docker, `127.0.0.1` otherwise).
- `MCP_PORT`: Port exposed by the MCP server (defaults to `8765` in Docker).
- `MCP_TRANSPORT`: Transport passed to `FastMCP.run` (set to `sse` in Docker for HTTP access).
