from __future__ import annotations

from concurrent import futures
from typing import Dict, Tuple

import grpc
from google.protobuf import empty_pb2

from examples.grpc_mcp_demo import job_pb2, job_pb2_grpc


class InMemoryJobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, job_pb2.Job] = {}

    def create_job(self, job: job_pb2.Job) -> job_pb2.Job:
        self._jobs[job.title] = job
        return job

    def get_job(self, title: str) -> job_pb2.Job | None:
        return self._jobs.get(title)

    def delete_job(self, title: str) -> bool:
        if title not in self._jobs:
            return False

        del self._jobs[title]
        return True


class JobService(job_pb2_grpc.JobServiceServicer):
    def __init__(self, store: InMemoryJobStore | None = None) -> None:
        self.store = store or InMemoryJobStore()

    def GetJob(self, request: job_pb2.JobRequest, context: grpc.ServicerContext) -> job_pb2.JobResponse:  # noqa: N802
        job = self.store.get_job(request.title)
        if not job:
            context.abort(grpc.StatusCode.NOT_FOUND, "Job not found")

        return job_pb2.JobResponse(job=job)

    def CreateJob(self, request: job_pb2.Job, context: grpc.ServicerContext) -> job_pb2.JobResponse:  # noqa: N802
        if not request.title:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Job title is required")

        created = self.store.create_job(job_pb2.Job(title=request.title, description=request.description))
        return job_pb2.JobResponse(job=created)

    def DeleteJob(self, request: job_pb2.JobRequest, context: grpc.ServicerContext) -> empty_pb2.Empty:  # noqa: N802
        deleted = self.store.delete_job(request.title)
        if not deleted:
            context.abort(grpc.StatusCode.NOT_FOUND, "Job not found")

        return empty_pb2.Empty()


def create_server(store: InMemoryJobStore | None = None, max_workers: int = 10) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    job_pb2_grpc.add_JobServiceServicer_to_server(JobService(store), server)
    return server


def serve(port: int = 50051, store: InMemoryJobStore | None = None) -> Tuple[grpc.Server, int]:
    server = create_server(store=store)
    actual_port = server.add_insecure_port(f"[::]:{port}")
    server.start()
    return server, actual_port


def main() -> None:
    server, port = serve()
    print(f"JobService listening on port {port}")
    server.wait_for_termination()


if __name__ == "__main__":
    main()
