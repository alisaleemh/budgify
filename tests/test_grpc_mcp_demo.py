from __future__ import annotations

import asyncio
import grpc
import pytest

from examples.grpc_mcp_demo import grpc_server, job_pb2, job_pb2_grpc, mcp_server


def test_grpc_server_crud_sequence() -> None:
    store = grpc_server.InMemoryJobStore()
    server, port = grpc_server.serve(port=0, store=store)
    channel = grpc.insecure_channel(f"localhost:{port}")
    stub = job_pb2_grpc.JobServiceStub(channel)

    try:
        created = stub.CreateJob(job_pb2.Job(title="engineer", description="Build things"))
        assert created.job.title == "engineer"
        assert created.job.description == "Build things"

        fetched = stub.GetJob(job_pb2.JobRequest(title="engineer"))
        assert fetched.job.title == "engineer"

        stub.DeleteJob(job_pb2.JobRequest(title="engineer"))

        with pytest.raises(grpc.RpcError) as excinfo:
            stub.GetJob(job_pb2.JobRequest(title="engineer"))
        assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND
    finally:
        channel.close()
        server.stop(0)


def test_mcp_tools_call_grpc() -> None:
    store = grpc_server.InMemoryJobStore()
    server, port = grpc_server.serve(port=0, store=store)
    address = f"localhost:{port}"

    async def _exercise_mcp_tools() -> None:
        created = await mcp_server.create_job(title="analyst", description="Check data", address=address)
        assert created == {"title": "analyst", "description": "Check data"}

        fetched = await mcp_server.get_job(title="analyst", address=address)
        assert fetched["description"] == "Check data"

        deleted = await mcp_server.delete_job(title="analyst", address=address)
        assert deleted == {"title": "analyst", "deleted": True}

    try:
        asyncio.run(_exercise_mcp_tools())
    finally:
        server.stop(0)
