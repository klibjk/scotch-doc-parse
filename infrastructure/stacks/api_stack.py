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

        # Permissions
        tasks_table.grant_read_write_data(start_task_fn)
        tasks_table.grant_read_data(get_result_fn)
        tasks_table.grant_read_write_data(bedrock_agent_fn)

        uploads_bucket.grant_read_write(bedrock_agent_fn)
        uploads_bucket.grant_read_write(presign_fn)
        reports_bucket.grant_read_write(bedrock_agent_fn)
        # Allow Lambdas to read LlamaParse secret
        from aws_cdk import aws_secretsmanager as secrets
        llama_secret = secrets.Secret.from_secret_name_v2(self, "LlamaParseSecret", "/scotch-doc-parse/llamaparse")
        llama_secret.grant_read(bedrock_agent_fn)

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
            key={"taskId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.taskId"))},
            update_expression="SET #status = :c, #result = :r, #completedAt = :t, #sessionId = :s",
            expression_attribute_names={
                "#status": "status",
                "#result": "result",
                "#completedAt": "completedAt",
                "#sessionId": "sessionId",
            },
            expression_attribute_values={
                ":c": tasks.DynamoAttributeValue.from_string("COMPLETED"),
                ":r": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.agent.agentResult")),
                ":t": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.agent.completedAt")),
                ":s": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.agent.sessionId")),
            },
        )
        handle_error = tasks.DynamoUpdateItem(
            self,
            "HandleError",
            table=tasks_table,
            key={"taskId": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.taskId"))},
            update_expression="SET #status = :f, #error = :e",
            expression_attribute_names={"#status": "status", "#error": "error"},
            expression_attribute_values={
                ":f": tasks.DynamoAttributeValue.from_string("FAILED"),
                ":e": tasks.DynamoAttributeValue.from_string(sfn.JsonPath.string_at("$.errorMessage")),
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
                allow_headers=["*"]
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
