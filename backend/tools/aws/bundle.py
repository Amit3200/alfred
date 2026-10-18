"""AWS tool bundle."""

from __future__ import annotations

from backend.tools.aws.tools import aws_tools
from backend.tools.base.bundle import ToolBundle
from backend.tools.base.tool import BaseTool


class AwsToolBundle(ToolBundle):
    capability_prefix = "aws"

    def tools(self) -> list[BaseTool]:
        return aws_tools()
