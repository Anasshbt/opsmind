"""
Lab Orchestrator — creates, manages, and destroys isolated lab environments.

Supports two backends:
  - DockerOrchestrator  (local dev / single node)
  - KubernetesOrchestrator (production)

Both implement the OrchestratorBase interface so the rest of the app is
backend-agnostic.
"""

from __future__ import annotations

import abc
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import docker
import structlog
from docker.errors import APIError, NotFound
from docker.models.containers import Container
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

from app.core.config import settings

logger = structlog.get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────

class SessionInfo:
    """Runtime info returned by the orchestrator after session creation."""

    def __init__(
        self,
        container_id: str,
        container_ip: str,
        expires_at: datetime,
    ) -> None:
        self.container_id = container_id
        self.container_ip = container_ip
        self.expires_at = expires_at


# ──────────────────────────────────────────────────────────────────────────────
# Abstract interface
# ──────────────────────────────────────────────────────────────────────────────

class OrchestratorBase(abc.ABC):
    @abc.abstractmethod
    async def create_session(
        self,
        session_id: uuid.UUID,
        image: str,
        cpu_limit: str,
        memory_limit: str,
        timeout_seconds: int,
        env_vars: dict[str, str],
    ) -> SessionInfo: ...

    @abc.abstractmethod
    async def destroy_session(self, container_id: str) -> None: ...

    @abc.abstractmethod
    async def exec_command(
        self, container_id: str, command: str
    ) -> tuple[int, str]: ...

    @abc.abstractmethod
    async def session_exists(self, container_id: str) -> bool: ...


# ──────────────────────────────────────────────────────────────────────────────
# Docker orchestrator
# ──────────────────────────────────────────────────────────────────────────────

class DockerOrchestrator(OrchestratorBase):
    """
    Spins up one Docker container per lab session.

    Security constraints applied to every container:
      - no-new-privileges
      - read-only root fs (with tmpfs for /tmp)
      - dropped all capabilities
      - isolated network (no internet, only lab net)
      - resource limits (cpu + memory)
      - runs as non-root (uid 1000)
    """

    def __init__(self) -> None:
        self._client = docker.from_env()
        self._ensure_network()

    def _ensure_network(self) -> None:
        try:
            self._client.networks.get(settings.DOCKER_NETWORK)
        except NotFound:
            self._client.networks.create(
                settings.DOCKER_NETWORK,
                driver="bridge",
                internal=True,  # no external internet access
                options={"com.docker.network.bridge.enable_icc": "false"},
            )
            logger.info("lab_network_created", network=settings.DOCKER_NETWORK)

    async def create_session(
        self,
        session_id: uuid.UUID,
        image: str,
        cpu_limit: str,
        memory_limit: str,
        timeout_seconds: int,
        env_vars: dict[str, str],
    ) -> SessionInfo:
        name = f"opsmind-lab-{session_id}"
        # Convert k8s-style CPU (e.g. "500m") → Docker nano_cpus
        nano_cpus = self._cpu_to_nano(cpu_limit)

        try:
            container: Container = self._client.containers.run(
                image=image,
                name=name,
                detach=True,
                network=settings.DOCKER_NETWORK,
                environment=env_vars,
                # Security
                user="1000:1000",
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                read_only=True,
                tmpfs={"/tmp": "size=64m,exec", "/run": "size=8m"},
                # Resources
                nano_cpus=nano_cpus,
                mem_limit=memory_limit,
                memswap_limit=memory_limit,  # disable swap
                # Misc
                stdin_open=True,
                tty=True,
                labels={
                    "opsmind.session_id": str(session_id),
                    "opsmind.managed": "true",
                },
            )
        except APIError as exc:
            logger.error("container_create_failed", session_id=str(session_id), error=str(exc))
            raise

        container.reload()
        ip = container.attrs["NetworkSettings"]["Networks"][settings.DOCKER_NETWORK]["IPAddress"]
        expires_at = datetime.now(UTC) + timedelta(seconds=timeout_seconds)

        logger.info("session_created", container=name, ip=ip)
        return SessionInfo(container_id=name, container_ip=ip, expires_at=expires_at)

    async def destroy_session(self, container_id: str) -> None:
        try:
            container = self._client.containers.get(container_id)
            container.stop(timeout=5)
            container.remove(force=True)
            logger.info("session_destroyed", container=container_id)
        except NotFound:
            logger.warning("session_not_found_on_destroy", container=container_id)
        except APIError as exc:
            logger.error("session_destroy_failed", container=container_id, error=str(exc))
            raise

    async def exec_command(self, container_id: str, command: str) -> tuple[int, str]:
        """Execute a command in the container and return (exit_code, output)."""
        try:
            container = self._client.containers.get(container_id)
            result = container.exec_run(
                cmd=["/bin/sh", "-c", command],
                user="1000",
                demux=False,
                stdout=True,
                stderr=True,
            )
            output = result.output.decode("utf-8", errors="replace") if result.output else ""
            return result.exit_code, output
        except (NotFound, APIError) as exc:
            return 1, str(exc)

    async def session_exists(self, container_id: str) -> bool:
        try:
            c = self._client.containers.get(container_id)
            return c.status == "running"
        except NotFound:
            return False

    @staticmethod
    def _cpu_to_nano(cpu_str: str) -> int:
        """Convert '500m' → 500_000_000 nano_cpus, '1' → 1_000_000_000."""
        if cpu_str.endswith("m"):
            millicores = int(cpu_str[:-1])
            return millicores * 1_000_000
        return int(float(cpu_str) * 1_000_000_000)


# ──────────────────────────────────────────────────────────────────────────────
# Kubernetes orchestrator
# ──────────────────────────────────────────────────────────────────────────────

class KubernetesOrchestrator(OrchestratorBase):
    """
    Creates a Kubernetes Pod per lab session in the opsmind-labs namespace.

    Pod spec enforces:
      - runAsNonRoot / runAsUser: 1000
      - allowPrivilegeEscalation: false
      - readOnlyRootFilesystem: true
      - dropped ALL capabilities
      - NetworkPolicy blocks egress (applied separately via k8s manifest)
      - resource requests + limits
    """

    def __init__(self) -> None:
        if settings.K8S_IN_CLUSTER:
            k8s_config.load_incluster_config()
        else:
            k8s_config.load_kube_config(config_file=settings.K8S_KUBECONFIG_PATH)
        self._core = k8s_client.CoreV1Api()
        self._namespace = settings.K8S_NAMESPACE

    async def create_session(
        self,
        session_id: uuid.UUID,
        image: str,
        cpu_limit: str,
        memory_limit: str,
        timeout_seconds: int,
        env_vars: dict[str, str],
    ) -> SessionInfo:
        pod_name = f"opsmind-lab-{session_id}"
        env = [k8s_client.V1EnvVar(name=k, value=v) for k, v in env_vars.items()]

        pod = k8s_client.V1Pod(
            metadata=k8s_client.V1ObjectMeta(
                name=pod_name,
                namespace=self._namespace,
                labels={
                    "app": "opsmind-lab",
                    "session-id": str(session_id),
                },
                annotations={
                    "opsmind.io/session-id": str(session_id),
                },
            ),
            spec=k8s_client.V1PodSpec(
                restart_policy="Never",
                automount_service_account_token=False,
                containers=[
                    k8s_client.V1Container(
                        name="lab",
                        image=image,
                        stdin=True,
                        tty=True,
                        env=env,
                        resources=k8s_client.V1ResourceRequirements(
                            requests={"cpu": "100m", "memory": "128Mi"},
                            limits={"cpu": cpu_limit, "memory": memory_limit},
                        ),
                        security_context=k8s_client.V1SecurityContext(
                            run_as_user=1000,
                            run_as_group=1000,
                            run_as_non_root=True,
                            allow_privilege_escalation=False,
                            read_only_root_filesystem=True,
                            capabilities=k8s_client.V1Capabilities(drop=["ALL"]),
                        ),
                        volume_mounts=[
                            k8s_client.V1VolumeMount(mount_path="/tmp", name="tmp"),
                        ],
                    )
                ],
                volumes=[
                    k8s_client.V1Volume(
                        name="tmp",
                        empty_dir=k8s_client.V1EmptyDirVolumeSource(medium="Memory", size_limit="64Mi"),
                    )
                ],
                security_context=k8s_client.V1PodSecurityContext(
                    run_as_non_root=True,
                    seccomp_profile=k8s_client.V1SeccompProfile(type="RuntimeDefault"),
                ),
            ),
        )

        self._core.create_namespaced_pod(namespace=self._namespace, body=pod)

        # Wait for pod IP (simple poll — replace with watch in production)
        import asyncio
        for _ in range(30):
            p = self._core.read_namespaced_pod(name=pod_name, namespace=self._namespace)
            if p.status and p.status.pod_ip:
                break
            await asyncio.sleep(1)

        pod_ip = p.status.pod_ip or ""
        expires_at = datetime.now(UTC) + timedelta(seconds=timeout_seconds)
        logger.info("k8s_session_created", pod=pod_name, ip=pod_ip)
        return SessionInfo(container_id=pod_name, container_ip=pod_ip, expires_at=expires_at)

    async def destroy_session(self, container_id: str) -> None:
        try:
            self._core.delete_namespaced_pod(
                name=container_id,
                namespace=self._namespace,
                body=k8s_client.V1DeleteOptions(grace_period_seconds=5),
            )
            logger.info("k8s_session_destroyed", pod=container_id)
        except k8s_client.rest.ApiException as exc:
            if exc.status == 404:
                logger.warning("k8s_pod_not_found", pod=container_id)
            else:
                raise

    async def exec_command(self, container_id: str, command: str) -> tuple[int, str]:
        from kubernetes.stream import stream

        ws = stream(
            self._core.connect_get_namespaced_pod_exec,
            name=container_id,
            namespace=self._namespace,
            command=["/bin/sh", "-c", command],
            container="lab",
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        output_lines: list[str] = []
        while ws.is_open():
            ws.update(timeout=settings.SCORING_TIMEOUT_SECONDS)
            if ws.peek_stdout():
                output_lines.append(ws.read_stdout())
            if ws.peek_stderr():
                output_lines.append(ws.read_stderr())

        exit_code = ws.returncode
        return exit_code or 0, "".join(output_lines)

    async def session_exists(self, container_id: str) -> bool:
        try:
            p = self._core.read_namespaced_pod(name=container_id, namespace=self._namespace)
            return p.status.phase == "Running" if p.status else False
        except k8s_client.rest.ApiException:
            return False


# ──────────────────────────────────────────────────────────────────────────────
# Factory
# ──────────────────────────────────────────────────────────────────────────────

def get_orchestrator() -> OrchestratorBase:
    if settings.ORCHESTRATOR == "kubernetes":
        return KubernetesOrchestrator()
    return DockerOrchestrator()
