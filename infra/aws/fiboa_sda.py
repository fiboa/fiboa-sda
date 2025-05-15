import os

from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_events,
    aws_iam as iam,
    aws_s3 as s3,
    aws_batch as batch,
    aws_s3_notifications,
    aws_sns as sns,
    Stack,
    Duration,
    Size,
)
from constructs import Construct


class FiboaSdaStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a VPC for the batch fargate cluster
        vpc = ec2.Vpc(self, "VPC")

        # Create AWS Batch Job Queue
        self.batch_queue = batch.JobQueue(self, "JobQueue")
        fargate_spot_environment = batch.FargateComputeEnvironment(
            self,
            "FargateSpotEnv",
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_NAT
            ),
            vpc=vpc,
            spot=True,
        )
        self.batch_queue.add_compute_environment(fargate_spot_environment, 0)

        # Task execution IAM role for Fargate
        task_execution_role = iam.Role(
            self,
            "TaskExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        # image_asset = ecr_assets.DockerImageAsset(
        #     self, "MyImageAsset",
        #     directory=os.path.join(os.getcwd(), "..")
        # )

        # Create Job Definition to submit job in batch job queue.
        batch.EcsJobDefinition(
            self,
            "MyJobDef",
            container=batch.EcsFargateContainerDefinition(
                self,
                "FargateCDKJobDef",
                image=ecs.ContainerImage.from_asset(
                    directory=os.path.join(os.getcwd(), "..")
                ),
                command=["ingest-one"],
                memory=Size.gibibytes(16),
                cpu=2,
                execution_role=task_execution_role,
            ),
        )

        # create lambda function
        # todo - create an IAM role with access to batch.
        # todo - inject environment
        function = _lambda.Function(
            self,
            "fiboa-s3-listener",
            runtime=_lambda.Runtime.FROM_IMAGE,
            handler=_lambda.Handler.FROM_IMAGE,
            architecture=_lambda.Architecture.ARM_64,
            timeout=Duration.seconds(10),
            code=_lambda.EcrImageCode.from_asset_image(
                directory=os.path.join(os.getcwd(), "lambda-image"),
            ),
        )

        # add SNS event source
        topic = sns.Topic.from_topic_arn(
            self,
            "source-coop-topic",
            topic_arn="arn:aws:sns:us-west-2:417712557820:us-west-2-opendata-source-coop_new-object"
        )
        event_source = lambda_events.SnsEventSource(
            topic,
            filter_policy={
                "S3Key": sns.SubscriptionFilter.string_filter(match_prefixes=['fiboa'])
            }
        )
        function.add_event_source(event_source)


        # # create s3 bucket
        # # bucket = s3.Bucket(self, "fiboa-sda-testing")
        # bucket = s3.Bucket.from_bucket_name(self, "source-coop-bucket", bucket_name="us-west-2.opendata.source.coop")

        # # create s3 notification for lambda function
        # # notification = aws_s3_notifications.LambdaDestination(function)

        # # assign notification for the s3 event type (ex: OBJECT_CREATED)
        # bucket.add_event_notification(
        #     s3.EventType.OBJECT_CREATED,
        #     notification,
        #     s3.NotificationKeyFilter(prefix="fiboa/*"),
        # )
