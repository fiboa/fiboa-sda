import os

from aws_cdk import (
    aws_lambda as _lambda,
    aws_s3 as _s3,
    aws_s3_notifications,
    Stack, Duration
)
from constructs import Construct

class FiboaSdaStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create a new container image
        ecr_image = _lambda.EcrImageCode.from_asset_image(
            directory=os.path.join(os.getcwd(), "lambda-image")
        )

        # create lambda function
        function = _lambda.Function(self, "fiboa-s3-listener",
                                    runtime=_lambda.Runtime.FROM_IMAGE,
                                    handler=_lambda.Handler.FROM_IMAGE,
                                    architecture=_lambda.Architecture.ARM_64,
                                    timeout=Duration.seconds(10), code=ecr_image)
        # create s3 bucket
        s3 = _s3.Bucket(self, "fiboa-sda-testing")

        # create s3 notification for lambda function
        notification = aws_s3_notifications.LambdaDestination(function)

        # assign notification for the s3 event type (ex: OBJECT_CREATED)
        s3.add_event_notification(_s3.EventType.OBJECT_CREATED, notification, _s3.NotificationKeyFilter(prefix="fiboa/*"))