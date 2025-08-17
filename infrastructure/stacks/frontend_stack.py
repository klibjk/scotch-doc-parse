from typing import Any
from aws_cdk import (
    Stack,
    RemovalPolicy,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    CfnOutput,
)
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct


class FrontendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: Any) -> None:
        super().__init__(scope, construct_id, **kwargs)

        site_bucket = s3.Bucket(
            self,
            "SiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Use S3Origin with Origin Access Identity so CloudFront can read from private bucket
        oai = cloudfront.OriginAccessIdentity(self, "OAI")
        # CloudFront Function to rewrite extension-less URLs to .html and add index.html for folders
        url_rewrite_fn = cloudfront.Function(
            self,
            "RewriteToHtml",
            code=cloudfront.FunctionCode.from_inline(
                """
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.endsWith('/')) {
    request.uri = uri + 'index.html';
  } else if (!uri.includes('.')) {
    request.uri = uri + '.html';
  }
  return request;
}
                """
            ),
        )

        distribution = cloudfront.Distribution(
            self,
            "SiteDistribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                function_associations=[cloudfront.FunctionAssociation(function=url_rewrite_fn, event_type=cloudfront.FunctionEventType.VIEWER_REQUEST)],
            ),
        )
        # Grant CloudFront OAI read access to the bucket
        site_bucket.grant_read(oai.grant_principal)

        # Deploy pre-built static site from frontend/nextjs-app/out
        s3deploy.BucketDeployment(
            self,
            "DeployWebsite",
            destination_bucket=site_bucket,
            sources=[s3deploy.Source.asset("frontend/nextjs-app/out")],
            distribution=distribution,
            distribution_paths=["/*"],
        )

        # Expose bucket name and distribution domain for use by CI/deploys
        CfnOutput(self, "SiteBucketName", value=site_bucket.bucket_name)
        CfnOutput(self, "DistributionDomainName", value=distribution.domain_name)
