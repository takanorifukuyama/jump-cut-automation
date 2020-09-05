import os
import json
import uuid
import boto3
from aws_lambda_powertools.logging import Logger
from botocore.exceptions import ClientError

STATE_MACHINE_ARN = os.getenv("STATE_MACHINE_ARN")

sfn = boto3.client("stepfunctions")
logger = Logger()


def start_state_machine(event, context):
    """
    S3 への動画アップロードをトリガーに Step Functions を起動する関数

    Parameters
    ----------
    event: S3 の ObjectCreated イベント
    context: Lambda 関数の実行コンテキスト

    Return
    ----------
    None

    """

    logger.info({"event": event})

    records = event["Records"]
    for record in records:
        file_name = record["s3"]["object"]["key"]
        job_name = str(uuid.uuid4())
        try:
            response = sfn.start_execution(
                name=job_name,
                input=json.dumps(
                    {
                        "job_name": job_name,
                        "file_name": file_name,
                        "iterator": {"index": 0},
                    }
                ),
                stateMachineArn=STATE_MACHINE_ARN,
            )
            logger.info({"response": response})
        except ClientError as e:
            logger.error({"error": e})
            raise

    return
