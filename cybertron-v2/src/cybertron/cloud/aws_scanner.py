"""AWS Security Scanner"""
from typing import Dict, List
import structlog
from cybertron.core import PluginInterface, TaskResult, TaskStatus, Finding, Severity

logger = structlog.get_logger()


class AWSSecurityScanner(PluginInterface):
    name = "aws_scanner"
    version = "2.0.0"
    description = "Scan AWS account for security misconfigurations"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        findings = []
        try:
            import boto3
            from botocore.exceptions import ClientError
            session = boto3.Session(profile_name=target if target != "localhost" else "default")

            s3 = session.client("s3")
            try:
                buckets = s3.list_buckets()["Buckets"]
                for bucket in buckets:
                    name = bucket["Name"]
                    try:
                        acl = s3.get_bucket_acl(Bucket=name)
                        for grant in acl.get("Grants", []):
                            grantee = grant.get("Grantee", {})
                            uri = grantee.get("URI", "")
                            if uri.endswith("AllUsers") or uri.endswith("AuthenticatedUsers"):
                                findings.append(Finding(
                                    title=f"Public S3 Bucket: {name}",
                                    description=f"Bucket {name} grants access to {uri}",
                                    severity=Severity.HIGH,
                                    category="cloud",
                                    target=name,
                                    remediation="Remove public ACLs"
                                ))
                    except ClientError:
                        pass
            except Exception as e:
                logger.warning("s3_scan_failed", error=str(e))

            ec2 = session.client("ec2")
            try:
                sgs = ec2.describe_security_groups()["SecurityGroups"]
                for sg in sgs:
                    for perm in sg.get("IpPermissions", []):
                        for ip_range in perm.get("IpRanges", []):
                            if ip_range.get("CidrIp") == "0.0.0.0/0":
                                findings.append(Finding(
                                    title=f"Open Security Group: {sg['GroupId']}",
                                    description=f"SG allows 0.0.0.0/0 on {perm.get('FromPort')}",
                                    severity=Severity.CRITICAL,
                                    category="cloud",
                                    target=sg["GroupId"],
                                    remediation="Restrict ingress to specific CIDR blocks"
                                ))
            except Exception as e:
                logger.warning("ec2_scan_failed", error=str(e))
        except ImportError:
            return TaskResult(
                task_id=__import__("uuid").uuid4().hex,
                status=TaskStatus.FAILED,
                error="boto3 not installed"
            )

        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings
        )


class DockerScanner(PluginInterface):
    name = "docker_scanner"
    version = "1.0.0"
    description = "Scan Docker daemon and containers for security issues"

    async def execute(self, target: str, options: Dict) -> TaskResult:
        findings = []
        try:
            import docker
            client = docker.from_env()
            for container in client.containers.list(all=True):
                info = container.attrs
                host_config = info.get("HostConfig", {})
                if host_config.get("Privileged", False):
                    findings.append(Finding(
                        title=f"Privileged Container: {container.name}",
                        description=f"Container {container.name} runs in privileged mode",
                        severity=Severity.CRITICAL,
                        category="container",
                        target=container.name,
                        remediation="Remove --privileged flag"
                    ))
                if host_config.get("NetworkMode") == "host":
                    findings.append(Finding(
                        title=f"Host Network Mode: {container.name}",
                        description="Container shares host network namespace",
                        severity=Severity.HIGH,
                        category="container",
                        target=container.name
                    ))
        except ImportError:
            return TaskResult(
                task_id=__import__("uuid").uuid4().hex,
                status=TaskStatus.FAILED,
                error="docker SDK not installed"
            )
        return TaskResult(
            task_id=__import__("uuid").uuid4().hex,
            status=TaskStatus.SUCCESS,
            findings=findings
        )
