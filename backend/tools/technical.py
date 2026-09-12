"""Read-only technical health, deployment, and log tools."""

from backend.data.database import SimulatedCompanyRepository
from backend.models.tools import EmptyInput, RecentDeploymentsInput, SystemLogsInput, ToolResult
from backend.tools.base import ReadOnlyTool


class ServiceHealthTool(ReadOnlyTool[EmptyInput]):
    name = "get_service_health"
    description = "Get overall and per-service operational health metrics."
    input_model = EmptyInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: EmptyInput) -> ToolResult:
        data = repository.get_collection("service_health")
        return ToolResult.success(self.name, f"Overall service status is {data['overall_status']}.", data)


class RecentDeploymentsTool(ReadOnlyTool[RecentDeploymentsInput]):
    name = "get_recent_deployments"
    description = "Get the most recent application deployments."
    input_model = RecentDeploymentsInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: RecentDeploymentsInput) -> ToolResult:
        deployments = repository.get_collection("deployments")[: arguments.limit]
        return ToolResult.success(self.name, f"Returned {len(deployments)} recent deployment(s).", {"deployments": deployments})


class SystemLogsTool(ReadOnlyTool[SystemLogsInput]):
    name = "get_system_logs"
    description = "Get recent logs, optionally filtered by service or severity."
    input_model = SystemLogsInput

    def execute(self, repository: SimulatedCompanyRepository, arguments: SystemLogsInput) -> ToolResult:
        logs = repository.get_collection("logs")
        if arguments.service:
            logs = [item for item in logs if item["service"] == arguments.service]
        if arguments.level:
            logs = [item for item in logs if item["level"] == arguments.level]
        logs = logs[: arguments.limit]
        return ToolResult.success(self.name, f"Returned {len(logs)} matching log record(s).", {"logs": logs})
