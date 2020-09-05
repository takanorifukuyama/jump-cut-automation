import os
import boto3
from boto3.dynamodb.conditions import Key
from aws_lambda_powertools.logging import Logger
from botocore.exceptions import ClientError

TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")

transcribe = boto3.client("transcribe")
dynamo = boto3.resource("dynamodb")
table = dynamo.Table(TABLE_NAME)
logger = Logger()


def check_transcribe_status(event, context):
    """
    Transcribe のジョブのステータスを確認し、完了まで待機する関数

    Parameter
    ----------
    - event: Step Functions からの入力
        - job_name: Transcribe の実行ジョブ名
        - iterator:
            - index: 何回目のステータス確認かを表すインデックス
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    - iterator:
        - index: 何回目のステータス確認かを表すインデックス
        - is_continue: 待機した後にもう一度ステータス確認を行うか示すフラグ
        - is_timeout: ステータス確認回数の上限を超えたかどうかを示すフラグ

    """

    logger.info({"event": event})
    job_name = event["job_name"]

    try:
        response = transcribe.get_transcription_job(
            TranscriptionJobName=job_name
        )
        logger.info({"transcribe_job_status": response})
    except ClientError as e:
        logger.error({"error": e})
        raise
    transcribe_status = response["TranscriptionJob"]["TranscriptionJobStatus"]

    max_count = 200
    index = event["iterator"]["index"]
    index += 1
    is_timeout = False
    is_continue = True
    if transcribe_status == "COMPLETED":
        is_continue = False
        index = 0
    elif index > max_count or transcribe_status == "FAILED":
        is_timeout = True
        is_continue = False

    iterator = {
        "index": index,
        "is_continue": is_continue,
        "is_timeout": is_timeout,
    }
    return iterator


def check_clipping_status(event, context):
    """
    DynamoDB のテーブルをチェックし、動画のカット処理が終了したか
    状態確認を行う関数

    Parameter
    ----------
    - event: Step Functions からの入力
        - job_name: Step Functions の実行名
        - iterator:
            - index: 何回目のステータス確認かを表すインデックス
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    - iterator:
        - index: 何回目のステータス確認かを表すインデックス
        - is_continue: 待機した後にもう一度ステータス確認を行うか示すフラグ
        - is_timeout: ステータス確認回数の上限を超えたかどうかを示すフラグ

    """

    logger.info({"event": event})
    job_name = event["job_name"]

    try:
        query_result = table.query(
            KeyConditionExpression=Key("job_name").eq(job_name)
        )
    except ClientError as e:
        logger.error({"error": e})
        raise

    max_count = 200
    index = event["iterator"]["index"]
    index += 1
    is_timeout = False
    is_continue = True
    if query_result["Count"] == 0:
        is_continue = False
        index = 0
    elif index > max_count:
        is_continue = False
        is_timeout = True

    iterator = {
        "index": index,
        "is_continue": is_continue,
        "is_timeout": is_timeout,
    }
    return iterator
