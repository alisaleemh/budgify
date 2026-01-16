from __future__ import annotations

import asyncio
import os
from typing import Any, Dict

import grpc
from mcp.server.fastmcp import FastMCP

from examples.grpc_mcp_demo import job_pb2, job_pb2_grpc

DEFAULT_TARGET = os.environ.get("GRPC_TARGET", "localhost:50051")
DEFAULT_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("MCP_PORT", "8000"))
DEFAULT_TRANSPORT = os.environ.get("MCP_TRANSPORT", "stdio")

server = FastMCP(
    name="job-grpc-demo",
    instructions="Expose a simple job board over gRPC so LLMs can experiment with MCP tools.",
    host=DEFAULT_HOST,
    port=DEFAULT_PORT,
)


def _call_grpc(method: str, address: str, **kwargs: Any) -> Dict[str, Any]:
    with grpc.insecure_channel(address) as channel:
        stub = job_pb2_grpc.JobServiceStub(channel)

        if method == "create":
            response = stub.CreateJob(job_pb2.Job(**kwargs))
            return {"title": response.job.title, "description": response.job.description}
        if method == "get":
            response = stub.GetJob(job_pb2.JobRequest(**kwargs))
            return {"title": response.job.title, "description": response.job.description}
        if method == "delete":
            stub.DeleteJob(job_pb2.JobRequest(**kwargs))
            return {"title": kwargs.get("title"), "deleted": True}

    raise ValueError("Unsupported gRPC method")


@server.tool(name="create_job", description="Create a job via the gRPC service")
async def create_job(title: str, description: str, address: str = DEFAULT_TARGET) -> Dict[str, Any]:
    return await asyncio.to_thread(_call_grpc, "create", address, title=title, description=description)


@server.tool(name="get_job", description="Fetch a job by title from the gRPC service")
async def get_job(title: str, address: str = DEFAULT_TARGET) -> Dict[str, Any]:
    return await asyncio.to_thread(_call_grpc, "get", address, title=title)


@server.tool(name="delete_job", description="Delete a job from the gRPC service")
async def delete_job(title: str, address: str = DEFAULT_TARGET) -> Dict[str, Any]:
    return await asyncio.to_thread(_call_grpc, "delete", address, title=title)


def main() -> None:
    server.run(transport=DEFAULT_TRANSPORT)


if __name__ == "__main__":
    main()
