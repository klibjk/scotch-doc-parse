from typing import Any
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_apigateway as apigw,
    aws_lambda as _lambda,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    CfnOutput,
)
from aws_cdk import aws_iam as iam
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_s3_notifications as s3n
from pathlib import Path
from constructs import Construct


class ApiStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Buckets
        uploads_bucket = s3.Bucket(
            self,
            "UploadsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        # Allow browser uploads via presigned URLs (CORS for PUT)
        uploads_bucket.add_cors_rule(
            allowed_methods=[s3.HttpMethods.PUT, s3.HttpMethods.GET, s3.HttpMethods.HEAD],
            allowed_origins=["*"],
            allowed_headers=["*"],
            exposed_headers=["ETag"],
            max_age=3000,
        )
        reports_bucket = s3.Bucket(
            self,
            "ReportsBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # DynamoDB tables
        tasks_table = dynamodb.Table(
            self,
            "AgentTasks",
            partition_key=dynamodb.Attribute(name="taskId", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="ttl",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Lambdas
        common_env = {
            "AGENT_TASKS_TABLE": tasks_table.table_name,
            "UPLOADS_BUCKET": uploads_bucket.bucket_name,
            "REPORTS_BUCKET": reports_bucket.bucket_name,
            # Secrets Manager ID where the LlamaParse API key is stored
            "LLAMAPARSE_SECRET_ID": "/scotch-doc-parse/llamaparse",
            "BEDROCK_MODEL_ID": "anthropic.claude-3-5-sonnet-20240620-v1:0",
        }

        start_task_fn = _lambda.Function(
            self,
            "StartTaskLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="start_task.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(30),
            environment=common_env,
        )
        get_result_fn = _lambda.Function(
            self,
            "GetResultLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="get_result.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(15),
            environment=common_env,
        )
        bedrock_agent_fn = _lambda.Function(
            self,
            "BedrockAgentLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="bedrock_agent.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(120),
            environment=common_env,
        )
        presign_fn = _lambda.Function(
            self,
            "GetPresignedUploadLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="get_presigned_upload.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(10),
            environment=common_env,
        )

        # Indexing ETL Lambda: parse->chunk->embed->write JSONL (reuses Reports bucket path)
        index_etl_fn = _lambda.Function(
            self,
            "IndexEtlLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="index_etl.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(120),
            environment={
                **common_env,
                # Optional embeddings model; can be set post-deploy
                "BEDROCK_EMBEDDINGS_MODEL_ID": os.environ.get("BEDROCK_EMBEDDINGS_MODEL_ID", ""),
            },
        )

        # Secrets
        from aws_cdk import aws_secretsmanager as secrets

        llama_secret = secrets.Secret.from_secret_name_v2(
            self, "LlamaParseSecret", "/scotch-doc-parse/llamaparse"
        )

        # Action Group Lambda for Bedrock Agent (parse_pdf)
        agent_tools_env = dict(common_env)
        parse_tool_fn = _lambda.Function(
            self,
            "AgentParsePdfTool",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="agent_tools.parse_pdf.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(60),
            environment=agent_tools_env,
        )
        uploads_bucket.grant_read(parse_tool_fn)
        llama_secret.grant_read(parse_tool_fn)

        # Permissions
        tasks_table.grant_read_write_data(start_task_fn)
        tasks_table.grant_read_data(get_result_fn)
        tasks_table.grant_read_write_data(bedrock_agent_fn)

        uploads_bucket.grant_read_write(bedrock_agent_fn)
        uploads_bucket.grant_read_write(presign_fn)
        reports_bucket.grant_read_write(bedrock_agent_fn)
        uploads_bucket.grant_read(index_etl_fn)
        reports_bucket.grant_read_write(index_etl_fn)
        # Allow Lambdas to read LlamaParse secret
        llama_secret.grant_read(bedrock_agent_fn)
        llama_secret.grant_read(index_etl_fn)
        # Allow invoking Bedrock models directly
        bedrock_agent_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:Converse",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:InvokeAgent",
                ],
                resources=["*"],
            )
        )
        # Allow embeddings model for ETL
        index_etl_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                ],
                resources=["*"],
            )
        )

        # S3 event notifications to kick off indexing when a new object is uploaded
        uploads_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(index_etl_fn),
            s3.NotificationKeyFilter(suffix=".pdf"),
        )
        uploads_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(index_etl_fn),
            s3.NotificationKeyFilter(suffix=".xlsx"),
        )

        # Step Functions state machine (skeleton)
        invoke_agent = tasks.LambdaInvoke(
            self,
            "InvokeBedrockAgent",
            lambda_function=bedrock_agent_fn,
            payload_response_only=True,
            result_path="$.agent",
            timeout=Duration.seconds(120),
        )
        update_result = tasks.DynamoUpdateItem(
            self,
            "UpdateResult",
            table=tasks_table,
            key={
                "taskId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.taskId"))
            },
            update_expression="SET #status = :c, #result = :r, #completedAt = :t, #sessionId = :s",
            expression_attribute_names={
                "#status": "status",
                "#result": "result",
                "#completedAt": "completedAt",
                "#sessionId": "sessionId",
            },
            expression_attribute_values={
                ":c": tasks.DynamoAttributeValue.from_string("COMPLETED"),
                ":r": tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.agent.agentResult")
                ),
                ":t": tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.agent.completedAt")
                ),
                ":s": tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.agent.sessionId")
                ),
            },
        )
        handle_error = tasks.DynamoUpdateItem(
            self,
            "HandleError",
            table=tasks_table,
            key={
                "taskId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.taskId"))
            },
            update_expression="SET #status = :f, #error = :e",
            expression_attribute_names={"#status": "status", "#error": "error"},
            expression_attribute_values={
                ":f": tasks.DynamoAttributeValue.from_string("FAILED"),
                ":e": tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.errorMessage")
                ),
            },
        )

        # On error, write FAILED via handle_error; on success continue to update_result
        definition = invoke_agent.add_catch(handle_error, result_path="$.error").next(update_result)

        state_machine = sfn.StateMachine(
            self,
            "AgentStateMachine",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.minutes(5),
        )

        # Allow StartTask to know and start the state machine
        state_machine.grant_start_execution(start_task_fn)
        start_task_fn.add_environment("SFN_ARN", state_machine.state_machine_arn)

        # API Gateway
        api = apigw.RestApi(
            self,
            "DocChatApi",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["*"],
            ),
        )

        agent_task = api.root.add_resource("agent-task")
        agent_task.add_method(
            "POST",
            apigw.LambdaIntegration(start_task_fn),
        )
        agent_task.add_method(
            "GET",
            apigw.LambdaIntegration(get_result_fn),
        )

        upload_request = api.root.add_resource("upload-request")
        upload_request.add_method(
            "POST",
            apigw.LambdaIntegration(presign_fn),
        )

        # Outputs that frontend might need would be added here in future
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "UploadsBucketName", value=uploads_bucket.bucket_name)
        CfnOutput(self, "ReportsBucketName", value=reports_bucket.bucket_name)

        # Grant Bedrock to invoke tool lambda (when Agent is configured)
        parse_tool_fn.add_permission(
            "AllowBedrockInvokeTool",
            principal=iam.ServicePrincipal("bedrock.amazonaws.com"),
            action="lambda:InvokeFunction",
        )

        # Load OpenAPI schema payload for inline embedding (works even if S3 schema location type is unavailable)
        openapi_payload = Path("infrastructure/agent/parse_openapi.json").read_text()

        # IAM Role for Bedrock Agent
        agent_role = iam.Role(
            self,
            "DocAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Execution role for Bedrock Agent",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaRole")
            ],
        )
        # Allow Agent to read schema from S3
        reports_bucket.grant_read(agent_role)

        # Define Bedrock Agent with inline action group using the AgentActionGroupProperty
        agent = bedrock.CfnAgent(
            self,
            "DocAgent",
            agent_name="ScotchDocAgent",
            # Use versioned model id per account setup
            foundation_model="anthropic.claude-3-5-sonnet-20240620-v1:0",
            instruction="You are a document analysis assistant. Use the action group tools to parse PDFs and answer questions grounded in parsed content.",
            idle_session_ttl_in_seconds=300,
            description="Parses and answers questions about uploaded PDFs",
            agent_resource_role_arn=agent_role.role_arn,
            action_groups=[
                bedrock.CfnAgent.AgentActionGroupProperty(
                    action_group_name="DocParseTools",
                    action_group_executor=bedrock.CfnAgent.ActionGroupExecutorProperty(
                        lambda_=parse_tool_fn.function_arn
                    ),
                    api_schema=bedrock.CfnAgent.APISchemaProperty(payload=openapi_payload),
                    action_group_state="ENABLED",
                )
            ],
        )
        agent_alias = bedrock.CfnAgentAlias(
            self,
            "DocAgentAlias",
            agent_alias_name="prod",
            agent_id=agent.attr_agent_id,
        )
        # Pass Agent identifiers to the Lambda via env
        bedrock_agent_fn.add_environment("BEDROCK_AGENT_ID", agent.attr_agent_id)
        bedrock_agent_fn.add_environment("BEDROCK_AGENT_ALIAS_ID", agent_alias.attr_agent_alias_id)
        CfnOutput(self, "BedrockAgentId", value=agent.attr_agent_id)
        CfnOutput(self, "BedrockAgentAliasId", value=agent_alias.attr_agent_alias_id)

        # Simple Agent chat proxy Lambda (frontend -> Agent)
        agent_chat_fn = _lambda.Function(
            self,
            "AgentChatLambda",
            runtime=_lambda.Runtime.PYTHON_3_11,
            handler="agent_chat.handler",
            code=_lambda.Code.from_asset("lambda"),
            timeout=Duration.seconds(60),
            environment={
                **common_env,
                "BEDROCK_AGENT_ID": agent.attr_agent_id,
                "BEDROCK_AGENT_ALIAS_ID": agent_alias.attr_agent_alias_id,
            },
        )
        agent_chat_fn.add_to_role_policy(
            iam.PolicyStatement(actions=["bedrock:InvokeAgent"], resources=["*"])
        )

        # API: POST /agent-chat -> AgentChatLambda
        agent_chat = api.root.add_resource("agent-chat")
        agent_chat.add_method("POST", apigw.LambdaIntegration(agent_chat_fn))
