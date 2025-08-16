#!/usr/bin/env python3
from aws_cdk import App, Tags

from stacks.api_stack import ApiStack
from stacks.frontend_stack import FrontendStack


app = App()

# Mandatory global tags per development plan
Tags.of(app).add("project_name", "scotch-doc-parser")
Tags.of(app).add("developer_name", "andresp")

api_stack = ApiStack(app, "ApiStack")
frontend_stack = FrontendStack(app, "FrontendStack")

app.synth()
