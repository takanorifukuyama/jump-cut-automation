import json
import os
from decimal import Decimal
import boto3
from aws_lambda_powertools.logging import Logger
from botocore.exceptions import ClientError

TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
QUEUE_NAME = os.getenv("SQS_QUEUE_NAME")
NO_SOUND_DURATION = Decimal(os.getenv("NO_SOUND_DURATION", "0.2"))
DIRECTORY = "/mnt/lambda"

dynamo = boto3.resource("dynamodb")
sqs = boto3.resource("sqs")
table = dynamo.Table(TABLE_NAME)
queue = sqs.get_queue_by_name(QueueName=QUEUE_NAME)
logger = Logger()


def analyze_speech(event, context):
    """
    動画の書き起こし結果から発話区間 (無音でない区間) を分析し、
    SQS と DynamoDB へ区間ごとに結果を送信・保存する関数

    Parameter
    ----------
    - event: Step Functions からの入力
        - job_name: Step Functions の実行名
        - file_name: S3 にアップロードされた動画のファイル名
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    - file_count: 生成される動画ファイル数

    """

    logger.info({"event": event})
    job_name = event["job_name"]
    file_name = event["file_name"]

    def clip_speech_activity(movie_start, movie_end, index):
        """
        発話区間のデータを SQS と DynamoDB へ書き込む関数

        Parameter
        ----------
        - movie_start: 発話区間の開始時間
        - movie_end: 発話区間の終了時間
        - index: 何番目の発話区間かを表すインデックス

        Return
        ----------
        - index: 次の発話区間のインデックス

        """

        duration = movie_end - movie_start
        if duration != 0:
            message = {
                "job_name": job_name,
                "index": index,
            }
            record = {
                **message,
                "file_name": file_name,
                "start_time": movie_start,
                "duration": duration,
            }
            try:
                queue.send_message(MessageBody=json.dumps(message))
                table.put_item(Item=record)
            except ClientError as e:
                logger.error({"error": e})
                raise
            index = index + 1
        return index

    transcription_path = f"{DIRECTORY}/{job_name}/input/transcription.json"
    try:
        with open(transcription_path, "r") as file:
            transcription = json.load(file)
    except json.JSONDecodeError as e:
        logger.error({"error": e})
        raise
    transcription_items = transcription["results"]["items"]

    last_movie_start = 0
    last_movie_end = 0
    next_index = 0
    for item in transcription_items:
        if item["type"] != "pronunciation":
            continue
        start_time = Decimal(item["start_time"])
        if start_time - last_movie_end >= NO_SOUND_DURATION:
            next_index = clip_speech_activity(
                last_movie_start, last_movie_end, next_index
            )
            last_movie_start = start_time
        last_movie_end = Decimal(item["end_time"])

    file_count = clip_speech_activity(
        last_movie_start, last_movie_end, next_index
    )
    return file_count
